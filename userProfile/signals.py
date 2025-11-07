# userProfile/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from django.db import transaction
from .models import Profile

@receiver(post_save, sender=User)
def create_or_update_user_profile(sender, instance, created, **kwargs):
    """
    - If user is created -> create Profile
    - If user updated -> ensure profile exists and save it
    Using transaction.on_commit ensures DB is stable (useful in tests/transactions).
    """
    if created:
        # Create profile after the transaction commits
        def _create_profile():
            Profile.objects.get_or_create(user=instance, defaults={'username': instance.username})
        transaction.on_commit(_create_profile)
    else:
        # If user updated and profile missing, create it
        try:
            instance.profile.save()
        except Profile.DoesNotExist:
            Profile.objects.create(user=instance, username=instance.username)
