# yatra_registration/admin_views.py

from django.shortcuts import get_object_or_404, render, redirect
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.db import transaction
from django.urls import reverse

from yatra.models import Yatra, YatraAccommodation, YatraJourney, YatraCustomFieldValue, YatraCustomField
from .models import *

@staff_member_required
def bulk_edit_view(request, yatra_id):
    yatra = get_object_or_404(Yatra, id=yatra_id)

    registrations = YatraRegistration.objects.filter(yatra=yatra,status__in=["partial", "paid", "attended"]).select_related(
        'registered_for'
    ).prefetch_related(
        'accommodation_allocations__accommodation',
        'journey_allocations__journey',
        'custom_values__custom_field_value__custom_field',
    )

    # Pre-build lookup for displaying selected custom field values
    custom_field_assignments = {}
    for reg in registrations:
        custom_field_assignments[reg.id] = {
            cfv.custom_field_value.custom_field_id: cfv.custom_field_value
            for cfv in reg.custom_values.all()
        }

    if request.method == "POST":
        with transaction.atomic():
            updated = 0

            selected_ids = request.POST.getlist("selected_regs")

            # Safety check
            if not selected_ids:
                messages.warning(request, "No devotees selected.")
                return redirect(request.path)

            target_regs = registrations.filter(id__in=selected_ids)

            for reg in target_regs:
            # for reg in registrations:
                changed = False  # Reset per registration

                # ==================== 1. ACCOMMODATIONS ====================
                # Delete removed
                keep_acc_uuids = [k.split('_')[-1] for k in request.POST if k.startswith(f'keep_acc_{reg.id}_')]
                deleted_acc = reg.accommodation_allocations.exclude(id__in=keep_acc_uuids).delete()[0]
                if deleted_acc:
                    changed = True

                # Update existing (room/bed)
                for key in request.POST:
                    if key.startswith('acc_room_'):
                        alloc_id = key.split('_')[-1]
                        if alloc_id not in keep_acc_uuids:
                            continue
                        try:
                            alloc = RegistrationAccommodation.objects.get(id=alloc_id, registration=reg)
                            old_room, old_bed = alloc.room_number, alloc.bed_number
                            new_room = request.POST.get(f'acc_room_{alloc_id}', '').strip() or None
                            new_bed = request.POST.get(f'acc_bed_{alloc_id}', '').strip() or None

                            if old_room != new_room or old_bed != new_bed:
                                alloc.room_number = new_room
                                alloc.bed_number = new_bed
                                alloc.save()
                                changed = True
                        except RegistrationAccommodation.DoesNotExist:
                            pass

                # Add new
                for key, acc_uuid in request.POST.items():
                    if key.startswith('new_acc_id_'):
                        parts = key.split('_')
                        reg_in_key = parts[3] if len(parts) >= 4 else None
                        if str(reg.id) != reg_in_key:
                            continue  # skip allocations not for this registration
                        suffix = key[len('new_acc_id_'):]
                        room = request.POST.get(f'new_acc_room_{suffix}', '').strip() or None
                        bed = request.POST.get(f'new_acc_bed_{suffix}', '').strip() or None
                        try:
                            acc_obj = YatraAccommodation.objects.get(id=acc_uuid)
                            obj, created = RegistrationAccommodation.objects.update_or_create(
                                registration=reg,
                                accommodation=acc_obj,
                                defaults={'room_number': room, 'bed_number': bed}
                            )
                            if created or obj.room_number != room or obj.bed_number != bed:
                                changed = True
                        except YatraAccommodation.DoesNotExist:
                            pass

                # ==================== 2. JOURNEYS ====================
                keep_journey_uuids = [k.split('_')[-1] for k in request.POST if k.startswith(f'keep_journey_{reg.id}_')]
                deleted_journey = reg.journey_allocations.exclude(id__in=keep_journey_uuids).delete()[0]
                if deleted_journey:
                    changed = True

                # Update existing (vehicle/seat)
                for key in request.POST:
                    if key.startswith('veh_'):
                        alloc_id = key.split('_')[-1]
                        if alloc_id not in keep_journey_uuids:
                            continue
                        try:
                            alloc = RegistrationJourney.objects.get(id=alloc_id, registration=reg)
                            old_veh, old_seat = alloc.vehicle_number, alloc.seat_number
                            new_veh = request.POST.get(f'veh_{alloc_id}', '').strip() or None
                            new_seat = request.POST.get(f'seat_{alloc_id}', '').strip() or None

                            if old_veh != new_veh or old_seat != new_seat:
                                alloc.vehicle_number = new_veh
                                alloc.seat_number = new_seat
                                alloc.save()
                                changed = True
                        except RegistrationJourney.DoesNotExist:
                            pass

                # Add new journeys
                for key, journey_uuid in request.POST.items():
                    if key.startswith('new_journey_id_'):
                        parts = key.split('_')
                        reg_in_key = parts[3] if len(parts) >= 4 else None
                        if str(reg.id) != reg_in_key:
                            continue # skip allocations not for this registration
                        suffix = key[len('new_journey_id_'):]
                        vehicle = request.POST.get(f'new_veh_{suffix}', '').strip() or None
                        seat = request.POST.get(f'new_seat_{suffix}', '').strip() or None
                        try:
                            journey_obj = YatraJourney.objects.get(id=journey_uuid)
                            obj, created = RegistrationJourney.objects.update_or_create(
                                registration=reg,
                                journey=journey_obj,
                                defaults={'vehicle_number': vehicle, 'seat_number': seat}
                            )
                            if created or obj.vehicle_number != vehicle or obj.seat_number != seat:
                                changed = True
                        except YatraJourney.DoesNotExist:
                            pass

                # ==================== 3. CUSTOM FIELDS ====================
                for cf in yatra.custom_fields.all():
                    val_id = request.POST.get(f"cf_{cf.id}_{reg.id}")
                    current = reg.custom_values.filter(custom_field=cf).first()
                    current_val_id = str(current.custom_field_value_id) if current else None

                    if val_id != current_val_id:
                        if val_id:
                            try:
                                value_obj = YatraCustomFieldValue.objects.get(id=val_id)
                                RegistrationCustomFieldValue.objects.update_or_create(
                                    registration=reg,
                                    custom_field=value_obj.custom_field,
                                    defaults={'custom_field_value': value_obj}
                                )
                                changed = True
                            except YatraCustomFieldValue.DoesNotExist:
                                pass
                        else:
                            reg.custom_values.filter(custom_field=cf).delete()
                            changed = True

                # Only count if something actually changed
                if changed:
                    updated += 1

            messages.success(request, f"Successfully updated {updated} devotee(s)!")
            # return redirect('admin:yatra_registration_bulk_edit', yatra_id=yatra.id)
            # return redirect('admin:yatra_registration_yatraregistration_changelist')
            return redirect(f"{reverse('admin:yatra_registration_yatraregistration_changelist')}?yatra__id__exact={yatra.id}")
            

    # GET request — show form
    context = {
        'title': f"Bulk Edit — {yatra.title}",
        'yatra': yatra,
        'registrations': registrations,
        'accommodations': YatraAccommodation.objects.filter(yatra=yatra),
        'journeys': YatraJourney.objects.filter(yatra=yatra),
        'custom_fields': yatra.custom_fields.all().prefetch_related('values'),
        'custom_field_assignments': custom_field_assignments,
        'opts': YatraRegistration._meta,
    }

    return render(request, "admin/yatra_registration/bulk_edit.html", context)
    