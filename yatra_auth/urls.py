# accounts/urls.py
from django.urls import path
from .views import (
    PasswordResetRequestView,
    PasswordResetConfirmView,
)

urlpatterns = [
    path('password/reset/', PasswordResetRequestView.as_view()),
    path("password/reset/confirm/", PasswordResetConfirmView.as_view()),
]
