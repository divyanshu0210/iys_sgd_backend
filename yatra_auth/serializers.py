from rest_framework import serializers
from django.contrib.auth.models import User
from userProfile.models import Profile


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