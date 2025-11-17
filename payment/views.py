from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser
from django.shortcuts import get_object_or_404
from django.db import transaction
from django.core.mail import send_mail
from django.conf import settings
from .models import *
from .serializers import *
from yatra.models import *
import qrcode # type: ignore
from io import BytesIO
from django.http import HttpResponse
import logging
import re
from rest_framework.decorators import api_view
# from rapidocr import RapidOCR
from django.http import JsonResponse
# from django.views.decorators.csrf import csrf_exempt



def generate_upi_qr(upi_id, amount, name, note="Yatra Payment"):
    upi_url = f"upi://pay?pa={upi_id}&pn={name}&am={amount}&cu=INR&tn={note}"
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(upi_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    buffer = BytesIO()
    img.save(buffer, format='PNG')
    return buffer.getvalue()

def upi_qr_view(request):
    amount = request.GET.get('amount')
    upi_id = request.GET.get('upi_id')
    qr_img = generate_upi_qr(upi_id, amount, "ISKCON Yatra")
    return HttpResponse(qr_img, content_type="image/png")

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
        payment, created = Payment.objects.get_or_create(
            total_amount=data["total_amount"],
            transaction_id=data["transaction_id"],
            uploaded_by=request.user.profile,
        )

        if created:
            logger.info(f"Created new Payment: id={payment.id}, txn={payment.transaction_id}, amount={payment.total_amount}")
        else:
            logger.warning(f"Reused existing Payment: id={payment.id}, txn={payment.transaction_id}")

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
                reg_inst.save()
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


# @csrf_exempt
# def verify_payment(request):
#     if request.method != "POST":
#         return JsonResponse({"error": "POST only"}, status=400)

#     if "file" not in request.FILES:
#         return JsonResponse({"error": "file missing"}, status=400)

#     image = request.FILES["file"]
#     expected_amount = request.POST.get("amount")

#     if not expected_amount:
#         return JsonResponse({"error": "amount missing"}, status=400)

#     try:
#         expected_amount_float = float(expected_amount.replace(",", ""))
#     except:
#         return JsonResponse({"error": "invalid amount"}, status=400)

#     # --- OCR ---
#     engine = RapidOCR()
#     image_bytes = image.read()
#     result = engine(image_bytes)

#     # ------ CORRECT WAY TO READ TEXT FROM RapidOCROutput ------
#     extracted_text = " ".join(result.txts)
#     print("OCR TEXT:", extracted_text)

#     # Normalize text
#     normalized_text = extracted_text.lower().replace(",", "").replace(" ", "")
#     amount_str = expected_amount.replace(",", "")

#     # ------ PAYMENT KEYWORDS ------
#     payment_keywords = [
#         "completed", "success", "successful", "payment", "paymentsuccessful",
#         "moneysent", "sent", "yousent", "youpayed", "paid", "paidto",
#         "credited", "debited", "received", "paymentdone",
#         "upi", "upiid", "upitransactionid", "upitransaction",
#         "refno", "referenceid", "transactionid", "txn", "txnid", "ref",
#         "googlepay", "gpay", "paytm", "phonepe", "bhim", "poweredbyupi",
#         "from:", "to:", "sentto",
#         "sbi", "hdfc", "icici", "axis", "kotak"
#     ]

#     has_keyword = any(kw in normalized_text for kw in payment_keywords)

#     # ------ EXACT AMOUNT MATCH ------
#     amount_patterns = set([
#         amount_str,                            # 20000
#         f"{expected_amount_float:.2f}",        # 20000.00
#         f"{expected_amount_float:.0f}",        # 20000
#     ])

#     found_amount = any(a in normalized_text for a in amount_patterns)

#     print("Amount patterns:", amount_patterns)
#     print("Keyword found:", has_keyword)
#     print("Amount match:", found_amount)

#     if not found_amount:
#         return JsonResponse({
#             "success": False,
#             "message": f"Amount mismatch. Expected amount ₹{expected_amount}."
#         })
    
#     if not has_keyword:
#         return JsonResponse({
#             "success": False,
#             "message": "Screenshot must contain UPI TransactionId/Reference No."
#         })

#     return JsonResponse({
#         "success": True,
#         "message": "Screenshot is valid to submit."
#     })
