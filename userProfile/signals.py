# userProfile/signals.py
from django.db.models.signals import post_save , pre_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone


from userProfile.utils import CENTER_CODE_MAP, DEFAULT_OTHER_CENTER_CODE, PENDING_APPROVAL_CODE, generate_member_id
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
        # def _create_profile():
        #     Profile.objects.get_or_create(user=instance, defaults={'username': instance.username})
        # transaction.on_commit(_create_profile)
        def _create_profile():
            with transaction.atomic():
                profile, is_created = Profile.objects.select_for_update().get_or_create(
                    user=instance,
                    defaults={
                        "username": instance.username,
                    }
                )

                print(profile)
                # Assign member_id only if missing
                if not profile.member_id:
                    year = timezone.now().year % 100  # YY
                    profile.member_id = generate_member_id(
                        year=f"{year:02d}",
                        center_code=PENDING_APPROVAL_CODE
                    )
                    profile.save(update_fields=["member_id"])

        transaction.on_commit(_create_profile)
    else:
        # If user updated and profile missing, create it
        try:
            instance.profile.save()
        except Profile.DoesNotExist:
            Profile.objects.create(user=instance, username=instance.username)



from .models import MentorRequest


# @receiver(post_save, sender=MentorRequest)
# def update_mentee_on_approval(sender, instance, **kwargs):
#     """
#     Update mentee's profile when a MentorRequest is approved or unapproved.
#     Works for both API and admin changes.
#     """
#     if not instance.pk:
#         # New request, nothing to do yet
#         return
#     mentee = instance.from_user

#     approval_year = timezone.now().year % 100  # YY
#     center_name = (mentee.center or "").lower().strip()
#     center_code = CENTER_CODE_MAP.get(
#         center_name,
#         DEFAULT_OTHER_CENTER_CODE)

#     if instance.is_approved:
#         with transaction.atomic():
#             new_member_id = generate_member_id(
#                 year=f"{approval_year:02d}",
#                 center_code=center_code
#             )

#             mentee.member_id = new_member_id
#             mentee.mentor = instance.to_mentor
#             mentee.user_type = "devotee"
#             mentee.save(update_fields=["member_id", "mentor", "user_type"])
#         # mentee.mentor = instance.to_mentor
#         # mentee.user_type = 'devotee'
#         # mentee.save(update_fields=['mentor', 'user_type'])
        
#     elif not instance.is_approved:
#         if mentee.mentor == instance.to_mentor:
#             with transaction.atomic():
#                 mentee.member_id = generate_member_id(
#                             year=f"{approval_year:02d}",
#                             center_code=PENDING_APPROVAL_CODE
#                         )
#                 mentee.mentor = None
#                 mentee.user_type = 'guest'
#                 mentee.save(update_fields=['mentor', 'user_type',"member_id"])



@receiver(pre_save, sender=MentorRequest)
def update_mentee_on_approval(sender, instance, **kwargs):
    """
    Handle MentorRequest approval transitions safely:
    - False -> True  : approve mentee
    - True  -> False : unapprove mentee
    """

    # ⛔ New request → do nothing
    if instance._state.adding:
        return  

    # Fetch previous DB state (now guaranteed to exist)
    previous = MentorRequest.objects.only("is_approved").get(pk=instance.pk)

    # No approval change → ignore
    if previous.is_approved == instance.is_approved:
        return

    mentee = instance.from_user
    approval_year = timezone.now().year % 100  # YY

    center_name = (mentee.center or "").lower().strip()
    center_code = CENTER_CODE_MAP.get(
        center_name,
        DEFAULT_OTHER_CENTER_CODE
    )

    # ✅ Approved (False → True)
    if not previous.is_approved and instance.is_approved:
        with transaction.atomic():
            mentee.member_id = generate_member_id(
                year=f"{approval_year:02d}",
                center_code=center_code
            )
            mentee.mentor = instance.to_mentor
            mentee.user_type = "devotee"
            mentee.save(update_fields=["member_id", "mentor", "user_type"])

    # ✅ Explicit unapproval (True → False)
    elif previous.is_approved and not instance.is_approved:
        with transaction.atomic():
            mentee.member_id = generate_member_id(
                year=f"{approval_year:02d}",
                center_code=PENDING_APPROVAL_CODE
            )
            mentee.mentor = None
            mentee.user_type = "guest"
            mentee.save(update_fields=["member_id", "mentor", "user_type"])