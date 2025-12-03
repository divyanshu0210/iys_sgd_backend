# yatra/admin_views.py
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib import messages
from django.db import transaction
from django.utils import timezone
from django.core.files.base import ContentFile
from .models import Yatra, YatraEligibility, YatraRegistration, YatraRegistrationInstallment, YatraInstallment
from payment.models import Payment
from userProfile.models import Profile
import openpyxl
import re
import requests


def download_drive_file(drive_url):
    """Download file from Google Drive public link (handles confirm page)"""
    if not drive_url or "drive.google.com" not in drive_url:
        return None, None

    file_id = None
    for pattern in [r"id=([a-zA-Z0-9_-]+)", r"/d/([a-zA-Z0-9_-]+)"]:
        match = re.search(pattern, drive_url)
        if match:
            file_id = match.group(1)
            break
    if not file_id:
        return None, None

    session = requests.Session()
    download_url = f"https://drive.google.com/uc?export=download&id={file_id}"
    resp = session.get(download_url, allow_redirects=True, stream=True)

    # Handle Google's virus scan warning page
    if "download_warning" in resp.cookies:
        confirm_token = resp.cookies.get("download_warning")
        download_url = f"https://drive.google.com/uc?export=download&id={file_id}&confirm={confirm_token}"
        resp = session.get(download_url, stream=True)

    if resp.status_code != 200:
        return None, None

    filename = "offline_proof.jpg"
    cd = resp.headers.get("Content-Disposition")
    if cd:
        import re
        match = re.findall('filename="?([^"]+)"?', cd)
        if match:
            filename = match[0]

    return filename, ContentFile(resp.content)


def yatra_bulk_offline_import(request, yatra_id):
    print("=== Starting yatra_bulk_offline_import ===")
    yatra = get_object_or_404(Yatra, id=yatra_id)
    print(f"Yatra: {yatra.title} (ID: {yatra.id})")

    if not request.user.is_superuser and not request.user.is_staff:
        messages.error(request, "Permission denied.")
        print("User does not have permission!")
        return redirect('admin:index')

    profiles = Profile.objects.filter(user_type__in=['devotee', 'mentor']).order_by('first_name', 'last_name')
    print(f"Profiles count: {profiles.count()}")

    eligible_ids = {str(pid) for pid in YatraEligibility.objects.filter(yatra=yatra, is_approved=True).values_list('profile_id', flat=True)}
    registered_ids = {str(pid) for pid in YatraRegistration.objects.filter(yatra=yatra).values_list('registered_for_id', flat=True)}
    print(f"Eligible profiles: {eligible_ids}")
    print(f"Registered profiles: {registered_ids}")

    profile_excel_map = {}  # str(profile.id) → {payment_type, screenshot_url}
    missing_profiles = []

    if request.method == "POST" and 'excel_file' in request.FILES:
        excel_file = request.FILES['excel_file']
        print("Excel file uploaded:", excel_file.name)
        try:
            wb = openpyxl.load_workbook(excel_file)
            sheet = wb.active
        except Exception as e:
            print("Error loading Excel:", e)
            messages.error(request, "Failed to read Excel file. Make sure it's valid.")
            sheet = None

        if sheet:
            for row in sheet.iter_rows(min_row=2, values_only=True):
                if len(row) < 13:
                    print("Skipping row (not enough columns):", row)
                    continue
                mobile = str(row[3]).strip() if row[3] else ""
                payment_text = str(row[11]).strip() if row[11] else ""
                screenshot_url = str(row[12]).strip() if row[12] else ""

                if mobile and mobile != "nan":
                    profile_excel_map[mobile] = {
                        "payment_type": payment_text,
                        "screenshot_url": screenshot_url
                    }
            print("Excel data parsed:", profile_excel_map)

            # Match by mobile
            for profile in profiles:
                mobile_key = str(profile.mobile or "").strip()
                if mobile_key and mobile_key in profile_excel_map:
                    profile_excel_map[str(profile.id)] = profile_excel_map.pop(mobile_key)
            print("Profile Excel map after matching by mobile:", profile_excel_map)
            request.session['offline_import_excel_map'] = profile_excel_map
            request.session.modified = True
            messages.success(request, f"Excel uploaded! Matched {len(profile_excel_map)} records by mobile.")

    elif request.method == "POST":
        selected = request.POST.getlist('profile')
        print("Selected profiles from form:", selected)
        profile_excel_map = request.session.get('offline_import_excel_map', {})
        print("Profile Excel map from session:", profile_excel_map)
        with transaction.atomic():
            success_count = 0
            for profile_id in selected:
                profile = get_object_or_404(Profile, id=profile_id)
                print(f"Processing profile: {profile.first_name} {profile.last_name} (ID: {profile_id})")

                excel_data = profile_excel_map.get(str(profile_id), {})
                drive_url = request.POST.get(f"drive_url_{profile_id}") or excel_data.get("screenshot_url", "")
                payment_type = excel_data.get("payment_type", "")
                print(f"Drive URL: {drive_url}, Payment Type: {payment_type}")

                target_installments = []
                if "3000" in payment_type and "Advance" in payment_type:
                    target_installments = list(yatra.installments.filter(amount=3000))
                elif "6500" in payment_type or "Full" in payment_type:
                    target_installments = list(yatra.installments.filter(amount__in=[3000, 3500, 6500]))

                print(f"Target installments: {[inst.label for inst in target_installments]}")

                if not drive_url or not target_installments:
                    missing_profiles.append(str(profile_id))
                    print(f"Missing data for profile {profile_id}. Skipping...")
                    continue

                # Auto-approve eligibility
                elig, _ = YatraEligibility.objects.get_or_create(
                    yatra=yatra, profile=profile,
                    defaults={'approved_by': request.user.profile, 'is_approved': True}
                )
                elig.is_approved = True
                elig.approved_by = request.user.profile
                elig.save()
                print(f"Eligibility approved for profile {profile_id}")

                # Create registration
                reg, _ = YatraRegistration.objects.get_or_create(
                    yatra=yatra, registered_for=profile,
                    defaults={'registered_by': request.user.profile}
                )
                reg.registered_by = request.user.profile
                reg.save()
                print(f"Registration saved for profile {profile_id}")

                # Process installments & payments
                filename, file_content = download_drive_file(drive_url)
                for inst in target_installments:
                    reg_inst, _ = YatraRegistrationInstallment.objects.get_or_create(
                        registration=reg, installment=inst
                    )
                    payment = Payment.objects.create(
                        transaction_id=f"OFFLINE-{profile.member_id}-{yatra.id}-{inst.id}",
                        total_amount=inst.amount,
                        uploaded_by=request.user.profile,
                        status='verified',
                        processed_by=request.user.profile,
                        processed_at=timezone.now(),
                        notes=f"Bulk imported by {request.user} on {timezone.now():%Y-%m-%d}"
                    )

                    if file_content:
                        payment.proof.save(filename or f"proof_{profile.member_id}_{inst.label}.jpg", file_content)
                        file_content = None  # use once per profile

                    reg_inst.payment = payment
                    reg_inst.is_paid = True
                    reg_inst.paid_at = timezone.now()
                    reg_inst.verified_by = request.user.profile
                    reg_inst.verified_at = timezone.now()
                    reg_inst.save()
                    print(f"Payment recorded for installment {inst.label} of profile {profile_id}")

                reg.update_status()
                success_count += 1
            print(f"Finished processing selected profiles. Success count: {success_count}, Missing: {missing_profiles}")

            if missing_profiles:
                messages.warning(request, f"Skipped {len(missing_profiles)} profiles (missing URL or payment info).")
            else:
                messages.success(request, f"Successfully imported {success_count} offline registrations!")
                if 'offline_import_excel_map' in request.session:
                    del request.session['offline_import_excel_map']
                return redirect('admin:yatra_yatra_changelist')

    context = {
        'yatra': yatra,
        'profiles': profiles,
        'installments': yatra.installments.all().order_by('amount'),
        'eligible_ids': eligible_ids,
        'registered_ids': registered_ids,
        'profile_excel_map': profile_excel_map,
        'missing_profiles': missing_profiles,
        'title': f"Bulk Offline Import – {yatra.title}",
    }
    print("=== Rendering template ===")
    return render(request, 'admin/yatra/bulk_offline_import.html', context)
