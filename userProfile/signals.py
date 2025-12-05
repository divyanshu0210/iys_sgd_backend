# userProfile/signals.py
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from django.db import transaction
from .models import *

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



from django.db.models.signals import pre_save
from django.dispatch import receiver
from .models import MentorRequest

@receiver(post_save, sender=MentorRequest)
def update_mentee_on_approval(sender, instance, **kwargs):
    """
    Update mentee's profile when a MentorRequest is approved or unapproved.
    Works for both API and admin changes.
    """
    if not instance.pk:
        # New request, nothing to do yet
        return
    mentee = instance.from_user
    if instance.is_approved:
        mentee.mentor = instance.to_mentor
        mentee.user_type = 'devotee'
        mentee.save(update_fields=['mentor', 'user_type'])
        
    elif not instance.is_approved:
        if mentee.mentor == instance.to_mentor:
            mentee.mentor = None
            mentee.user_type = 'guest'
            mentee.save(update_fields=['mentor', 'user_type'])
