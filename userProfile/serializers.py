from rest_framework import serializers
from .models import *
from django.conf import settings
from django.core.cache import cache
from rest_framework import serializers
from .models import Profile
from .utils import resolve_bace_for_center

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
    counsellor_name = serializers.SerializerMethodField()

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
            'iskcon_introduction_date',
            'iskcon_introduced_by',
            'first_connected_center',
            'email_consent',
            'address',
            'emergency_contact',
            'mentor',
            'mentor_name',
            'counsellor_name',
            'profile_picture',
            'profile_picture_url',
            'no_of_chanting_rounds',
            'created_at',
            'is_profile_approved',
            'profile_approved_at',
            'profile_verification_status',
        ]
        read_only_fields = [
            'member_id',
            'user_type',
            'mentor',
            'profile_verification_status',
        ]

    def get_full_name(self, obj):
        return f"{obj.first_name or ''} {obj.last_name or ''}".strip()
    
    def get_mentor_name(self, obj):
        if obj.mentor:
            return f"{obj.mentor.first_name} {obj.mentor.last_name}".strip()
        return None

    def get_counsellor_name(self, obj):
        counsellor = None
        if obj.mentor and obj.mentor.user_type == 'counsellor':
            counsellor = obj.mentor
        elif obj.center:
            bace = resolve_bace_for_center(obj.center)
            counsellor = bace.counsellor if bace else None
        return counsellor.full_name() if counsellor else None

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
                obj.profile_verification_status == 'verified' or
                obj.user_type == 'mentor' or
                obj.user_type == 'counsellor' or
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


class BaceSerializer(serializers.ModelSerializer):
    counsellor_name = serializers.SerializerMethodField()
    mentor_ids = serializers.SerializerMethodField()
    other_centers = serializers.SerializerMethodField()

    class Meta:
        model = Bace
        fields = ['id', 'name', 'is_active', 'counsellor', 'counsellor_name', 'mentor_ids', 'other_centers']

    def get_counsellor_name(self, obj):
        return obj.counsellor.full_name() if obj.counsellor else None

    def get_mentor_ids(self, obj):
        return list(obj.mentors.values_list('id', flat=True))

    def get_other_centers(self, obj):
        return list(obj.other_centers.filter(is_active=True).values_list('name', flat=True))




class ProfileFastSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source='user.email', read_only=True)
    mentor_member_id = serializers.IntegerField(source='mentor.member_id', allow_null=True)
    # Fix: point to the actual related field
    mentor_name = serializers.CharField(source='mentor.full_name', allow_null=True, default=None)
    profile_picture = serializers.SerializerMethodField()

    def get_profile_picture(self, obj):
        """Cache expensive R2 signed-URL generation for repeated list reads."""
        if not obj.profile_picture:
            return None

        cache_key = f"profile-picture-url:{obj.pk}:{obj.profile_picture.name}"
        cached_url = cache.get(cache_key)
        if cached_url is None:
            cached_url = obj.profile_picture.url
            # Keep this below the usual signed-URL lifetime.
            cache.set(cache_key, cached_url, timeout=300)
        return cached_url

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
            'initiated_name',
            'no_of_chanting_rounds',
            'profile_picture',
            'profile_verification_status',
        ]







