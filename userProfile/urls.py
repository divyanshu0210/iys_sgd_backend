
from django.contrib import admin
from django.urls import path
from userProfile.views import *
urlpatterns = [
    path('yatras/', YatraListView.as_view(), name='yatra-list'),
    path('yatras/<uuid:yatra_id>/register/', YatraRegisterView.as_view(), name='yatra-register'),
    path('profile/', ProfileView.as_view(), name='profile'),
    path('profile/upload-picture/', ProfilePictureUploadView.as_view(), name='profile-picture-upload'),
    path('mentor/requests/', MentorRequestView.as_view(), name='mentor_requests'),
    path('mentor/requests/<uuid:request_id>/', MentorRequestView.as_view(), name='mentor_request_action'),
    path('mentor/dashboard/', MentorDashboardView.as_view(), name='mentor_dashboard'),


]