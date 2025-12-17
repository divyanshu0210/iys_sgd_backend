from rest_framework import serializers
from django.contrib.auth.models import User
from userProfile.models import Profile

from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils.http import urlsafe_base64_decode
from django.contrib.auth.models import User
# accounts/serializers.py
from django.contrib.auth.models import User
from rest_framework import serializers




class RegisterSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = User
        fields = ['username', 'email', 'password', 'full_name']
        extra_kwargs = {'password': {'write_only': True}}

    def create(self, validated_data):
        full_name = validated_data.pop('full_name', None)
        user = User.objects.create_user(**validated_data)
    # Update profile created by signal
        if hasattr(user, "profile"):
            user.profile.full_name = full_name or user.username
            user.profile.save()
        return user
    

class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        if not User.objects.filter(email=value).exists():
            raise serializers.ValidationError("No user with this email")
        return value


class PasswordResetConfirmSerializer(serializers.Serializer):
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(min_length=8)

    def validate(self, data):
        try:
            uid = urlsafe_base64_decode(data["uid"]).decode()
            user = User.objects.get(pk=uid)
        except Exception:
            raise serializers.ValidationError("Invalid user")

        token_generator = PasswordResetTokenGenerator()
        if not token_generator.check_token(user, data["token"]):
            raise serializers.ValidationError("Invalid or expired token")

        data["user"] = user
        return data
