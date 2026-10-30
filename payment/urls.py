
from django.contrib import admin
from django.urls import path
from userProfile.views import *
from .views import *
from .donation_api import DonationSubmitView

urlpatterns = [
    path('donations/', DonationSubmitView.as_view(), name='donation-submit'),
    path('<uuid:yatra_id>/batch-payment-proof/', BatchPaymentProofView.as_view(), name='batch-payment-proof'),
    path(
            '<uuid:payment_id>/upload-screenshot/',
            UploadPaymentScreenshotView.as_view(),
            name='upload-payment-screenshot'
        )
]