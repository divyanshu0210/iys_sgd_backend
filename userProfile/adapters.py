# userProfile/adapters.py
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied

User = get_user_model()

class MySocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        """
        Called just after a successful social login, before the login is actually processed.
        """
        email = sociallogin.account.extra_data.get('email')
        if not email:
            return

        try:
            # check if user already exists
            user = User.objects.get(email=email)
            # connect this social account to existing user
            sociallogin.connect(request, user)
        except User.DoesNotExist:
            # pass  # new user → normal flow
            raise PermissionDenied(
                "Account doesn’t exist. Sign up to create a new account."
            )
