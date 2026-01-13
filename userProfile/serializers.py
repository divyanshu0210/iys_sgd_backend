from rest_framework import serializers
from .models import *
from django.conf import settings
from rest_framework import serializers
from .models import Profile

class MentorField(serializers.Field):
    """Custom field to handle mentor <-> member_id mapping"""
    def to_representation(self, value):
        # When returning data to frontend
        if value is None:
            return None
        return value.member_id  # ✅ Show mentor's member_id

    def to_internal_value(self, data):
        # When receiving data from frontend
        from .models import Profile
        if data in [None, ""]:
            return None
        try:
            return Profile.objects.get(member_id=int(data))
        except (Profile.DoesNotExist, ValueError, TypeError):
            raise serializers.ValidationError("Invalid mentor member_id.")


class ProfileSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    profile_picture_url = serializers.SerializerMethodField()
    email = serializers.SerializerMethodField()
    is_profile_approved = serializers.SerializerMethodField()
    profile_approved_at = serializers.SerializerMethodField()
    mentor = MentorField(required=False, allow_null=True)  # ✅ use our custom field
    mentor_name = serializers.SerializerMethodField()

    class Meta:
        model = Profile
        fields = [
            'id',
            'member_id',
            'user_type',
            'username',
            'first_name',
            'last_name',
            'full_name',
            'email',
            'dob',
            'gender',
            'marital_status',
            'mobile',
            'aadhar_card_no',
            'country',
            'center',
            'is_initiated',
            'initiated_name',
            'spiritual_master',
            'initiation_date',
            'initiation_place',
            'email_consent',
            'address',
            'emergency_contact',
            'mentor',
            'mentor_name',
            'profile_picture',
            'profile_picture_url',
            'no_of_chanting_rounds',
            'created_at',
            'is_profile_approved',
            'profile_approved_at',
        ]

    def get_full_name(self, obj):
        return f"{obj.first_name or ''} {obj.last_name or ''}".strip()
    
    def get_mentor_name(self, obj):
        if obj.mentor:
            return f"{obj.mentor.first_name} {obj.mentor.last_name}".strip()
        return None

    def get_profile_picture_url(self, obj):
        request = self.context.get('request')
        if obj.profile_picture and hasattr(obj.profile_picture, 'url'):
            return request.build_absolute_uri(obj.profile_picture.url) if request else obj.profile_picture.url
        return None

    def get_email(self, obj):
        return obj.user.email if obj.user else None

    def get_is_profile_approved(self, obj):
        try:
            return (
                obj.user_type == 'mentor' or
                obj.received_requests.filter(is_approved=True).exists()
                or obj.sent_requests.filter(is_approved=True).exists()
            )
        except:
            return False
        
    def get_profile_approved_at(self, obj):
    # Case 1: someone approved this user as a mentee
        received = obj.received_requests.filter(
            is_approved=True
        ).order_by("-approved_at").first()

        # Case 2: this user was approved by someone else
        sent = obj.sent_requests.filter(
            is_approved=True
        ).order_by("-approved_at").first()

        # Case 3: if user is a mentor, they are automatically approved from creation
        # if obj.user_type == 'mentor':
        #     return obj.created_at

        # Pick the most recent approval
        req = received or sent
        return req.approved_at if req else None




class ProfileFastSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source='user.email', read_only=True)
    mentor_member_id = serializers.IntegerField(source='mentor.member_id', allow_null=True)
    # Fix: point to the actual related field
    mentor_name = serializers.CharField(source='mentor.full_name', allow_null=True, default=None)

    class Meta:
        model = Profile
        fields = [
            'id',
            'member_id',
            'user_type', 
            'first_name',
            'last_name',
            'full_name',
            'dob',
            'gender',
            'mobile',
            'email',
            'center',
            'mentor_member_id',
            'mentor_name',
            'is_initiated',
            'no_of_chanting_rounds',
            'profile_picture',
        ]







