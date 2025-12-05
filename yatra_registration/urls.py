
from django.contrib import admin
from django.urls import path
from userProfile.views import *
from .views import *

urlpatterns = [
    path('<uuid:yatra_id>/eligibility/', YatraEligibilityView.as_view(), name='yatra-eligibility'),
    path('<uuid:yatra_id>/register/', YatraRegistrationView.as_view(), name='yatra-register'),
    path('<uuid:yatra_id>/<uuid:profile_id>/registrations/', 
        YatraRegistrationDetailView.as_view(), 
        name='yatra-registration-detail'),

]