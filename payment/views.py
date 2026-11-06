from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view,permission_classes,authentication_classes
from django.db import IntegrityError, transaction
from django.core.mail import send_mail
from django.conf import settings
from yatra_registration.models import *
from .models import *
from .serializers import *
from yatra.models import *
from io import BytesIO
from django.http import HttpResponse
import logging
from decimal import Decimal
from rest_framework.exceptions import PermissionDenied, ValidationError
from userProfile.scopes import can_access_profile
from rest_framework import status, permissions
from django.db import connection
from django.http import JsonResponse
from payment.notifications import notify_payment_submitted
from yatra_registration.payment_rules import payment_block_reason
import json
from types import SimpleNamespace

logger = logging.getLogger(__name__)

class BatchPaymentProofView(APIView):
    """
    Creates a Payment entry and links it to multiple YatraRegistrationInstallments.
    """
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, yatra_id):
        if not getattr(request, '_atomic_checkout', False):
            return Response({'error': 'Submit payment and proof together at checkout.'}, status=400)
        serializer = BatchPaymentProofSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        actor = request.user.profile
        get_object_or_404(Yatra, pk=yatra_id)

        # Validate and lock every registration before creating a payment:
        # a bad member, installment, amount, or duplicate must reject the batch.
        linked = []
        seen = set()
        total = Decimal("0")
        for item in data["registration_installments"]:
            profile = get_object_or_404(Profile, pk=item["profile_id"])
            if not can_access_profile(actor, profile):
                raise PermissionDenied("You cannot submit payment for this profile.")
            registration = get_object_or_404(
                YatraRegistration.objects.select_for_update(),
                registered_for=profile, yatra_id=yatra_id,
            )
            if registration.status in {"cancelled", "refunded", "substituted", "attended"}:
                raise ValidationError("Payment cannot be submitted for this registration.")
            for label in item["installments"]:
                key = (registration.pk, label)
                if key in seen:
                    raise ValidationError("An installment was selected more than once.")
                seen.add(key)
                inst = YatraRegistrationInstallment.objects.select_for_update(of=("self",)).select_related(
                    "installment", "payment",
                ).filter(
                    registration=registration, installment__label=label,
                    installment__yatra_id=yatra_id, installment__phase_id=registration.phase_id,
                ).first()
                if not inst:
                    raise ValidationError(f"Invalid or unselected installment: {label}.")
                if inst.is_paid:
                    raise ValidationError(f"Installment {label} is already verified.")
                if inst.payment and inst.payment.status != "rejected" and inst.payment.proof:
                    raise ValidationError(f"Installment {label} already has a payment under review.")
                reason = payment_block_reason(registration, inst.installment)
                if reason:
                    raise ValidationError(reason)
                linked.append(inst)
                total += inst.installment.amount

        if not linked:
            raise ValidationError("Select at least one installment.")
        if data["total_amount"] != total:
            raise ValidationError("The payment amount must match the selected installments.")
        screenshot = request.FILES.get('screenshot')
        if not screenshot:
            raise ValidationError({'screenshot': 'A payment screenshot is required.'})

        try:
            with transaction.atomic():
                payment = Payment.objects.create(
                    transaction_id=data["transaction_id"],
                    total_amount=total,
                    uploaded_by=actor,
                    proof=screenshot,
                )
        except IntegrityError:
            raise ValidationError({"transaction_id": "This transaction ID has already been used."})

        for inst in linked:
            inst.payment = payment
            inst.verified_by = None
            inst.verified_at = None
            inst.save(update_fields=["payment", "verified_by", "verified_at"])
        for registration in {inst.registration for inst in linked}:
            registration.update_status()

        transaction.on_commit(lambda: notify_payment_submitted(payment), robust=True)

        return Response({
            "payment_id": str(payment.id),
            "linked_installments": len(linked),
            "message": f"Payment proof submitted for {len(linked)} installments.",
        }, status=status.HTTP_201_CREATED)


class AtomicCheckoutView(APIView):
    """Commit registrations, payment, and proof as a single checkout."""
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    @transaction.atomic
    def post(self, request, yatra_id):
        from yatra_registration.views import YatraRegistrationView

        screenshot = request.FILES.get('screenshot')
        if not screenshot:
            raise ValidationError({'screenshot': 'A payment screenshot is required.'})
        try:
            registrations = json.loads(request.data.get('registrations', ''))
            selected = json.loads(request.data.get('registration_installments', ''))
        except (TypeError, ValueError):
            raise ValidationError('Invalid registration or installment data.')
        if not isinstance(registrations, dict):
            raise ValidationError('Invalid registration data.')
        payment_data = {
            'transaction_id': request.data.get('transaction_id'),
            'total_amount': request.data.get('total_amount'),
            'registration_installments': selected,
        }
        serializer = BatchPaymentProofSerializer(data=payment_data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        items = serializer.validated_data['registration_installments']
        profile_ids = [str(item['profile_id']) for item in items]
        if len(profile_ids) != len(set(profile_ids)) or any(pid not in registrations for pid in profile_ids):
            raise ValidationError('Each payment must have matching registration details.')
        for pid in profile_ids:
            profile = get_object_or_404(Profile, pk=pid)
            if not can_access_profile(request.user.profile, profile):
                raise PermissionDenied('You cannot submit payment for this profile.')
        payload = {pid: registrations[pid] for pid in profile_ids}
        for item in items:
            registration = payload[str(item['profile_id'])]
            if not isinstance(registration, dict):
                raise ValidationError('Invalid registration details.')
            selected_labels = registration.get('installments_selected', [])
            if not isinstance(selected_labels, list) or not all(isinstance(label, str) for label in selected_labels) or not set(item['installments']).issubset(selected_labels):
                raise ValidationError('Payment installments do not match the registration.')

        existing = Payment.objects.filter(transaction_id=serializer.validated_data['transaction_id'], uploaded_by=request.user.profile).first()
        if existing and existing.proof and existing.status != 'rejected' and existing.total_amount == serializer.validated_data['total_amount']:
            expected = {(str(item['profile_id']), label) for item in items for label in item['installments']}
            previous = list(existing.installments.select_related('registration', 'installment'))
            actual = {(str(inst.registration.registered_for_id), inst.installment.label) for inst in previous if inst.installment and inst.registration.yatra_id == yatra_id}
            if len(expected) == sum(len(item['installments']) for item in items) == len(previous) and expected == actual:
                return Response({'payment_id': str(existing.pk), 'message': 'Payment proof was already submitted.'}, status=200)

        internal = SimpleNamespace(user=request.user, data=payload, _atomic_checkout=True)
        response = YatraRegistrationView().post(internal, yatra_id)
        if response.status_code >= 400 or response.data.get('errors'):
            raise ValidationError(response.data.get('errors') or response.data.get('error') or 'Registration failed.')
        internal.data = payment_data
        internal.FILES = request.FILES
        response = BatchPaymentProofView().post(internal, yatra_id)
        if response.status_code >= 400:
            raise ValidationError(response.data)
        payment_id = response.data['payment_id']
        return Response({'payment_id': payment_id, 'message': 'Payment proof submitted successfully.'}, status=201)
    

class UploadPaymentScreenshotView(APIView):
    """
    Attach screenshot to an existing Payment
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    @transaction.atomic
    def post(self, request, payment_id):
        payment = get_object_or_404(Payment, id=payment_id, uploaded_by=request.user.profile)

        if payment.status != "under_review":
            return Response({"error": "This payment can no longer be changed."}, status=400)

        file = request.FILES.get("screenshot")
        if not file:
            return Response({"error": "No screenshot provided."}, status=status.HTTP_400_BAD_REQUEST)

        for inst in payment.installments.select_related('registration__phase', 'registration__yatra', 'installment'):
            reason = payment_block_reason(inst.registration, inst.installment)
            if reason:
                return Response({'error': reason}, status=400)

        payment.proof = file
        payment.save(update_fields=["proof"])
        transaction.on_commit(lambda: notify_payment_submitted(payment), robust=True)

        return Response({
            "message": "Screenshot uploaded successfully.",
            "proof_url": request.build_absolute_uri(payment.proof.url)
        })

