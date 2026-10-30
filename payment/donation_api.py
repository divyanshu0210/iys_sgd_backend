from decimal import Decimal

from django.db import IntegrityError
from rest_framework import serializers, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from .models import Donation, Payment


class DonationSerializer(serializers.ModelSerializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0.01"))
    screenshot = serializers.ImageField()

    class Meta:
        model = Donation
        fields = ("donor_name", "initiated_name", "address", "mobile", "amount",
                  "pan", "email", "transaction_id", "screenshot")
        extra_kwargs = {
            "initiated_name": {"required": False, "allow_blank": True},
            "pan": {"required": False, "allow_blank": True},
        }

    def validate_transaction_id(self, value):
        if Payment.objects.filter(transaction_id=value).exists():
            raise serializers.ValidationError("This transaction ID has already been used for a payment.")
        return value

    def validate_screenshot(self, file):
        if file.size > 5 * 1024 * 1024:
            raise serializers.ValidationError("Screenshot must be 5 MB or smaller.")
        return file


class DonationThrottle(AnonRateThrottle):
    rate = "300/hour"


class DonationSubmitView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    parser_classes = [MultiPartParser, FormParser]
    throttle_classes = [DonationThrottle]

    def post(self, request):
        serializer = DonationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            donation = serializer.save()
        except IntegrityError:
            return Response({"transaction_id": ["This transaction ID has already been submitted."]},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response({"id": str(donation.pk), "message": "Donation submitted successfully."},
                        status=status.HTTP_201_CREATED)
