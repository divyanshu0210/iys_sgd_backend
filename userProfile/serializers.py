from rest_framework import serializers
from .models import Yatra, Profile, YatraRegistration
from dj_rest_auth.serializers import PasswordResetSerializer
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
    mentor = MentorField(required=False, allow_null=True)  # ✅ use our custom field

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
            'profile_picture',
            'profile_picture_url',
            'no_of_chanting_rounds',
            'created_at',
            'is_profile_approved',
        ]

    def get_full_name(self, obj):
        return f"{obj.first_name or ''} {obj.last_name or ''}".strip()

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



class YatraSerializer(serializers.ModelSerializer):
    class Meta:
        model = Yatra
        fields = '__all__'

class YatraRegistrationSerializer(serializers.ModelSerializer):
    registered_for_name = serializers.SerializerMethodField()
    registrant_name = serializers.SerializerMethodField()

    class Meta:
        model = YatraRegistration
        fields = [
            'id',
            'yatra',
            'registrant',
            'registrant_name',
            'registered_for',
            'registered_for_name',
            'status',
            'registered_at'
        ]

    def get_registered_for_name(self, obj):
        return f"{obj.registered_for.first_name or ''} {obj.registered_for.last_name or ''}".strip()

    def get_registrant_name(self, obj):
        return f"{obj.registrant.first_name or ''} {obj.registrant.last_name or ''}".strip()





