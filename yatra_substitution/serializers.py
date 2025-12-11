

# -------------------------------
# Substitution Request Serializer

from userProfile.serializers import ProfileSerializer
from yatra_registration.models import *
from .models import SubstitutionRequest
from rest_framework import serializers

class SubstitutionRequestSerializer(serializers.ModelSerializer):
    initiator = ProfileSerializer(read_only=True)
    target_profile = ProfileSerializer(read_only=True)
    registration = serializers.PrimaryKeyRelatedField(read_only=True)

    # NEW FIELD
    is_target_eligible = serializers.SerializerMethodField()
    is_target_registered = serializers.SerializerMethodField()

    class Meta:
        model = SubstitutionRequest
        fields = "__all__"
        read_only_fields = (
            "two_digit_code", "created_at", "status", "amount_paid",
            "accepted_at", "expires_at"
        )

    def get_is_target_eligible(self, obj):
        # obj.target_profile is the receiver side profile
        return YatraEligibility.objects.filter(
            yatra=obj.registration.yatra,
            profile=obj.target_profile,
            is_approved=True
        ).exists()  
    
    def get_is_target_registered(self, obj):
        # obj.target_profile is the receiver side profile
        return YatraRegistration.objects.filter(
            yatra=obj.registration.yatra,
            registered_for=obj.target_profile,
        ).exists()

