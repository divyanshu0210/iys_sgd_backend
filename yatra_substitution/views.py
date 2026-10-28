from django.shortcuts import render

# Create your views here.
# views.py
from rest_framework import status, permissions
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db import transaction
import secrets
from decimal import Decimal

from userProfile.models import Profile
from yatra_registration.models import *
from .models import SubstitutionRequest
from .serializers import SubstitutionRequestSerializer
from django.db import models




SUB_CODE_TTL_MINUTES = 30
MAX_CODE_ATTEMPTS = 5

def initiator_has_verified_installment(registration):
    # Replace with your installment model structure
    return registration.installments.filter(is_paid=True, verified_by__isnull=False).exists()

def compute_amount_paid_by_initiator(registration):
    # Sum paid verified installment amounts (or adapt)
    paid = registration.installments.filter(is_paid=True).aggregate(total=models.Sum('installment__amount'))['total'] or Decimal(0)
    return Decimal(paid)

def target_is_approved(yatra, profile):
    return YatraEligibility.objects.filter(
        yatra=yatra,
        profile=profile,
        is_approved=True
    ).exists()


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
@transaction.atomic
def create_substitution_request(request, reg_id):
    user_profile = request.user.profile
    reg = get_object_or_404(YatraRegistration.objects.select_for_update().select_related("yatra"), id=reg_id)
    if reg.registered_for != user_profile:
        return Response({"detail": "Only the registrant can initiate substitution."}, status=403)

    if not reg.yatra.is_substitution_open or reg.yatra.close_yatra:
        return Response({"detail": "Substitution is closed for this Yatra."}, status=400)

    if SubstitutionRequest.objects.filter(
        registration=reg, status="pending", expires_at__gt=timezone.now(),
    ).exists():
        return Response({"detail": "An active substitution request already exists."}, status=400)

    if reg.status not in ["paid", "partial"]:
        return Response({"detail": "Registration is not active."}, status=400)

    if not initiator_has_verified_installment(reg):
        return Response({"detail": "At least one installment must be fully verified to initiate substitution."}, status=400)
    
      # NEW: block if any installment is under verification
    if reg.has_any_installment_under_verification():
        return Response(
            {"detail": "Substitution is not allowed because an installment verification is pending."},
            status=400
        )

    target_id = request.data.get("target_profile_id")
    if not target_id:
        return Response({"detail":"Missing target_profile_id"}, status=400)
    try:
        target = Profile.objects.get(member_id=target_id)
    except (Profile.DoesNotExist, ValueError, TypeError):
        return Response({"detail":"Target profile not found"}, status=404)
    
     # NEW: prevent self-substitution
    if target == user_profile:
        return Response(
            {"detail": "You cannot send a substitution request to yourself."},
            status=400
        )

    # Generate an unpredictable code; old two-digit requests remain valid.
    code = f"{secrets.randbelow(1_000_000):06d}"

    amount_paid = compute_amount_paid_by_initiator(reg)

    expires_at = timezone.now() + timezone.timedelta(minutes=SUB_CODE_TTL_MINUTES)

    sr = SubstitutionRequest.objects.create(
        registration=reg,
        initiator=user_profile,
        target_profile=target,
        two_digit_code=code,
        expires_at=expires_at,
        amount_paid=amount_paid,
    )

    # TODO: notify target (via notification table / websocket)
    # return code to initiator (so initiator can show it)
    return Response({
        "request_id": str(sr.id),
        "two_digit_code": code,
        "amount_paid": str(amount_paid),
        "cancellation_fee": str(reg.yatra.cancellation_fee),
        "expires_at": sr.expires_at.isoformat(),
    }, status=201)



@api_view(['GET'])
@permission_classes([permissions.IsAuthenticated])
def get_existing_substitution_request(request, reg_id):
    """
    Return existing active substitution request (if any)
    for this registration initiated by this user.
    """
    user_profile = request.user.profile
    reg = get_object_or_404(YatraRegistration, id=reg_id)

    # Only the initiator of substitution can view
    if reg.registered_for != user_profile:
        return Response(
            {"detail": "Not allowed to view substitution request."},
            status=403
        )

    # Get latest active request (not expired & not accepted)
    sr = (
        SubstitutionRequest.objects
        .filter(registration=reg, initiator=user_profile, status="pending")
        .order_by('-created_at')
        .first()
    )

    if not sr:
        return Response({"has_request": False}, status=200)

    # If expired, do not show
    if sr.expires_at < timezone.now():
        return Response({"has_request": False}, status=200)

    return Response({
        "has_request": True,
        "request": {
            "request_id": str(sr.id),
            "two_digit_code": sr.two_digit_code,
            "amount_paid": str(sr.amount_paid),
            "cancellation_fee": str(reg.yatra.cancellation_fee),
            "expires_at": sr.expires_at.isoformat(),
        }
    }, status=200)


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def list_substitution_requests(request):
    user_profile = request.user.profile
    qs = SubstitutionRequest.objects.filter(target_profile=user_profile, status="pending").filter(
        models.Q(expires_at__isnull=True) | models.Q(expires_at__gt=timezone.now())
    ).order_by("-created_at")
    serializer = SubstitutionRequestSerializer(qs, many=True)
    return Response(serializer.data)
    


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
@transaction.atomic
def respond_substitution_request(request, req_id):
    # payload: { action: "accept" | "reject", code: "12" }
    user_profile = request.user.profile
    # Lock the request during code checks so parallel guesses share one limit.
    sr = get_object_or_404(SubstitutionRequest.objects.select_for_update().select_related("registration__yatra"), id=req_id)
    if sr.target_profile != user_profile:
        return Response({"detail":"Not authorized"}, status=403)
    if sr.status != "pending":
        return Response({"detail":"Request not pending"}, status=400)
    if sr.expires_at and sr.expires_at < timezone.now():
        sr.delete()  # DELETE RECORD
        return Response({"detail":"Request expired"}, status=400)

    action = request.data.get("action")
    if action == "reject":
        sr.delete()  # DELETE RECORD
        return Response({"detail":"Rejected"}, status=200)

    if action != "accept":
        return Response({"detail": "Invalid action."}, status=400)
    if not sr.registration.yatra.is_substitution_open or sr.registration.yatra.close_yatra:
        return Response({"detail": "Substitution is closed for this Yatra."}, status=400)

    # accept flow
    code = request.data.get("code")
    if code is None:
        return Response({"detail":"Missing code"}, status=400)
    if sr.failed_code_attempts >= MAX_CODE_ATTEMPTS:
        return Response({"detail": "Too many incorrect attempts. Ask for a new request."}, status=429)
    code = str(code)
    if not code.isascii() or not code.isdigit() or not secrets.compare_digest(code, sr.two_digit_code):
        sr.failed_code_attempts += 1
        sr.save(update_fields=["failed_code_attempts"])
        return Response({"detail":"Invalid code"}, status=400)

    # ensure target profile is approved
    # if not user_profile.is_profile_approved:
    if not target_is_approved(sr.registration.yatra, user_profile):
        return Response({"detail":"Your profile is not approved"}, status=400)
    if YatraRegistration.objects.filter(yatra=sr.registration.yatra, registered_for=user_profile).exists():
        return Response({"detail": "You are already registered for this Yatra."}, status=400)

    # perform transfer atomically
    with transaction.atomic():
        reg = YatraRegistration.objects.select_for_update().get(pk=sr.registration_id)
        if reg.registered_for_id != sr.initiator_id or reg.status not in {"paid", "partial"}:
            return Response({"detail": "The original registration is no longer eligible for substitution."}, status=400)
        if reg.has_any_installment_under_verification():
            return Response({"detail": "An installment is awaiting verification."}, status=400)

        # create a new registration for target with same details OR reassign existing reg
        # approach: create copy but preserve original record for audit
        new_reg = YatraRegistration.objects.create(
            yatra=reg.yatra,
            registered_for=sr.target_profile,
            registered_by=reg.registered_by,
            phase=reg.phase,
            form_data=reg.form_data,
            status=reg.status,
        )
        # mark old registration as substituted and record
        reg.status = "substituted"
        reg.substituted_to = sr.target_profile
        reg.substitution_date = timezone.now()
        reg.save()

        # transfer child objects: accommodations, journeys, custom values, installments
        # assuming models RegistrationAccommodation, RegistrationJourney, RegistrationCustomFieldValue exist
        reg.accommodation_allocations.update(registration=new_reg)

        # 2. Journeys
        reg.journey_allocations.update(registration=new_reg)

        # 3. Custom field values
        reg.custom_values.update(registration=new_reg)

        # 4. Installments (keep the same payment references)
        reg.installments.update(registration=new_reg)

        sr.status = "accepted"
        sr.accepted_at = timezone.now()
        sr.processed_by = user_profile
        sr.new_registration = new_reg
        sr.save()

    # Notify initiator & target about success

    return Response({"detail":"Substitution completed", "new_registration_id": str(new_reg.id)})
