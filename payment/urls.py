
from django.contrib import admin
from django.urls import path
from userProfile.views import *
from .views import *
from .donation_api import DonationSubmitView

urlpatterns = [
    path('account-details/', PaymentAccountView.as_view(), name='payment-account-details'),
    path('donations/', DonationSubmitView.as_view(), name='donation-submit'),
    path('<uuid:yatra_id>/checkout/', AtomicCheckoutView.as_view(), name='atomic-checkout'),
]
