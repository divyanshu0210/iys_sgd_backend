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

logger = logging.getLogger(__name__)

class BatchPaymentProofView(APIView):
    """
    Creates a Payment entry and links it to multiple YatraRegistrationInstallments.
    """
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, yatra_id):
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
                linked.append(inst)
                total += inst.installment.amount

        if not linked:
            raise ValidationError("Select at least one installment.")
        if data["total_amount"] != total:
            raise ValidationError("The payment amount must match the selected installments.")

        try:
            with transaction.atomic():
                payment = Payment.objects.create(
                    transaction_id=data["transaction_id"],
                    total_amount=total,
                    uploaded_by=actor,
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

        return Response({
            "payment_id": str(payment.id),
            "linked_installments": len(linked),
            "message": f"Payment entry created and linked to {len(linked)} installments. Please upload proof next.",
        }, status=status.HTTP_201_CREATED)
    

class UploadPaymentScreenshotView(APIView):
    """
    Attach screenshot to an existing Payment
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, payment_id):
        payment = get_object_or_404(Payment, id=payment_id, uploaded_by=request.user.profile)

        if payment.status != "under_review":
            return Response({"error": "This payment can no longer be changed."}, status=400)

        file = request.FILES.get("screenshot")
        if not file:
            return Response({"error": "No screenshot provided."}, status=status.HTTP_400_BAD_REQUEST)

        payment.proof = file
        payment.save(update_fields=["proof"])

        transaction.on_commit(lambda: notify_payment_submitted(payment))

        return Response({
            "message": "Screenshot uploaded successfully.",
            "proof_url": request.build_absolute_uri(payment.proof.url)
        })

