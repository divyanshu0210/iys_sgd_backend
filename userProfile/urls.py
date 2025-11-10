
from django.contrib import admin
from django.urls import path
from userProfile.views import *
urlpatterns = [
    path('profile/', ProfileView.as_view(), name='profile'),
    path('profile/upload-picture/', ProfilePictureUploadView.as_view(), name='profile-picture-upload'),
    path('mentor/requests/', MentorRequestView.as_view(), name='mentor_requests'),
    path('mentor/requests/<uuid:request_id>/', MentorRequestView.as_view(), name='mentor_request_action'),
    path('yatras/', YatraListView.as_view(), name='yatra-list'),
    # Yatra eligibility approvals (new)
    path('yatras/<uuid:yatra_id>/eligibility/', YatraEligibilityView.as_view(), name='yatra-eligibility'),
    # Existing Yatra registration (updated, but same path)
    path('yatras/<uuid:yatra_id>/register/', YatraRegisterView.as_view(), name='yatra-register'),
    # urls.py
    path('api/yatras/<uuid:yatra_id>/batch-payment-proof/', BatchPaymentProofView.as_view()),
    # urls.py
    path('qr/', upi_qr_view),
    


]