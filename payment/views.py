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
from rest_framework import status, permissions
from django.db import connection
from django.http import JsonResponse

@api_view(["GET"])
@permission_classes([permissions.AllowAny])
@authentication_classes([])
def keep_alive(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1;")
            result = cursor.fetchone()[0]
        return JsonResponse({
            "app": "ok",
            "db": "ok",
            "db_response": result
        })
    except Exception as e:
        return JsonResponse({
            "app": "ok",
            "db": "down",
            "error": str(e)
        }, status=503)
# def keep_alive(request):
#     with connection.cursor() as cursor:
#             cursor.execute("SELECT 1;")
#     return Response({"message": "Hi"})


logger = logging.getLogger(__name__)

class BatchPaymentProofView(APIView):
    """
    Creates a Payment entry and links it to multiple YatraRegistrationInstallments.
    """
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, yatra_id):
        logger.info(f"[BatchPaymentProofView] POST request by user={request.user} for yatra_id={yatra_id}")

        serializer = BatchPaymentProofSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        logger.debug(f"Validated data: {data}")

        # --- Step 1: Create or get Payment record ---
        # payment, created = Payment.objects.get_or_create(
        #     total_amount=data["total_amount"],
        #     transaction_id=data["transaction_id"],
        #     uploaded_by=request.user.profile,
        # )
        try:
            payment = Payment.objects.create(
                transaction_id=data["transaction_id"],
                total_amount=data["total_amount"],
                uploaded_by=request.user.profile,
            )
            logger.info(f"Created new Payment: id={payment.id}, txn={payment.transaction_id}, amount={payment.total_amount}")

        except IntegrityError:
            return Response(
                {
                    "error": "This transaction ID has already been used."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # if created:
        # else:
        #     logger.warning(f"Reused existing Payment: id={payment.id}, txn={payment.transaction_id}")

        linked_count = 0

        # --- Step 2: Iterate through each registration group ---
        for reg_item in data["registration_installments"]:
            profile_id = reg_item["profile_id"]
            installment_labels = reg_item["installments"]
            logger.debug(f"Processing profile_id={profile_id} with installments={installment_labels}")

            # ✅ Fetch the Profile instance first
            try:
                profile = Profile.objects.get(id=profile_id)
            except Profile.DoesNotExist:
                logger.error(f"Profile not found for id={profile_id}, skipping.")
                continue

            # ✅ Then fetch registration for this profile and yatra
            try:
                registration = YatraRegistration.objects.get(
                    registered_for=profile,
                    yatra_id=yatra_id
                )
            except YatraRegistration.DoesNotExist:
                logger.error(f"No registration found for profile={profile_id} and yatra={yatra_id}, skipping.")
                continue

            # ✅ Fetch installments matching the given labels
            installments = YatraInstallment.objects.filter(
                yatra_id=yatra_id,
                label__in=installment_labels
            )
            if not installments.exists():
                logger.warning(f"No matching installments found for labels={installment_labels} in yatra={yatra_id}")
                continue

            for inst in installments:
                reg_inst, created = YatraRegistrationInstallment.objects.get_or_create(
                    registration=registration,
                    installment=inst,
                )
                reg_inst.payment = payment
                reg_inst.verified_by = None
                reg_inst.verified_at = None
                reg_inst.save()
                reg_inst.registration.update_status()
                linked_count += 1
                logger.info(
                    f"Linked installment '{inst.label}' (₹{inst.amount}) "
                    f"to registration={registration.id}, payment={payment.id}"
                )

        logger.info(f"Finished linking {linked_count} installments to Payment {payment.id}")

        return Response({
            "payment_id": str(payment.id),
            "linked_installments": linked_count,
            "message": f"✅ Payment entry created and linked to {linked_count} installments successfully. Please upload proof next."
        }, status=status.HTTP_201_CREATED)  
    

class UploadPaymentScreenshotView(APIView):
    """
    Attach screenshot to an existing Payment
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, payment_id):
        payment = get_object_or_404(Payment, id=payment_id, uploaded_by=request.user.profile)

        file = request.FILES.get("screenshot")
        if not file:
            return Response({"error": "No screenshot provided."}, status=status.HTTP_400_BAD_REQUEST)

        payment.proof = file
        payment.save(update_fields=["proof"])

        return Response({
            "message": "Screenshot uploaded successfully.",
            "proof_url": request.build_absolute_uri(payment.proof.url)
        })

