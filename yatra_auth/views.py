# accounts/views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth.models import User
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.core.mail import send_mail
from .serializers import (
    PasswordResetRequestSerializer,
    PasswordResetConfirmSerializer,
)
from rest_framework.permissions import AllowAny
from allauth.account.views import ConfirmEmailView
from django.shortcuts import redirect
from django.http import Http404
from django.conf import settings
import logging

logger = logging.getLogger(__name__)
class CustomConfirmEmailView(ConfirmEmailView):
    def get(self, request, *args, **kwargs):
        try:
            self.object = self.get_object()
            self.object.confirm(request)
            return redirect(f"{settings.FRONTEND_BASE_URL}email-verified")
        except Http404:
            return redirect(f"{settings.FRONTEND_BASE_URL}email-already-verified")
        

class PasswordResetRequestView(APIView):
    permission_classes = [AllowAny]  # <- add this
    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data["email"]
        user = User.objects.get(email=email)

        token = PasswordResetTokenGenerator().make_token(user)
        uid = urlsafe_base64_encode(force_bytes(user.pk))

        reset_link = f"{settings.FRONTEND_BASE_URL}reset-password/{uid}/{token}"

        try:
            send_mail(
                subject="Password Reset",
                message=f"Click the link to reset password:\n{reset_link}",
                from_email=f'{settings.DEFAULT_FROM_EMAIL}',
                recipient_list=[email],
            )
        except Exception as e:
            logger.exception("Password reset email failed")
            return Response(
                {"detail": "Unable to send email. Please try again later."},
                status=500
            )

        return Response(
            {"message": "Password reset link sent"},
            status=status.HTTP_200_OK,
        )
    
class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]  # <- add this
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = serializer.validated_data["user"]
        new_password = serializer.validated_data["new_password"]
        token = serializer.validated_data["token"]

        user.set_password(new_password)
        user.save()
        PasswordResetTokenGenerator().check_token(user, token)

        return Response(
            {"message": "Password reset successful"},
            status=status.HTTP_200_OK,
        )

