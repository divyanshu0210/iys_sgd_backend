
from django.contrib import admin
from django.urls import path
from userProfile.views import *
urlpatterns = [
    path('baces/', BaceListView.as_view(), name='bace-list'),
    path('profile/', ProfileView.as_view(), name='profile'),
    path('mentor/requests/', MentorRequestView.as_view(), name='mentor_requests'),
    path('mentor/requests/<uuid:request_id>/', MentorRequestView.as_view(), name='mentor_request_action'),
    path("proxy-image/", proxy_image),
]
