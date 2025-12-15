from django.utils import timezone
from django.db import models, transaction
import uuid
from django.contrib.auth.models import User
import os
import uuid
from django.db import models
# models.py


def profile_picture_upload_path(instance, filename):
    """
    Generate a unique profile picture filename using the member_id.
    If member_id exists, it overwrites the previous image automatically.
    """
    ext = filename.split('.')[-1].lower()

    # ✅ If the user already has a member_id, use it as the filename.
    if instance.member_id:
        filename = f"{instance.member_id}.{ext}"
    else:
        # Fallback for brand new users (member_id not assigned yet)
        filename = f"temp_{uuid.uuid4()}.{ext}"

    return os.path.join('profile_pics', filename) 



def profile_picture_upload_path(instance, filename):
    return f"profile_pictures/{instance.user.username}/{filename}"

class Profile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')

    # 🔹 Sequential 6-digit member ID
    # member_id = models.PositiveIntegerField(unique=True, editable=False)
    member_id = models.PositiveIntegerField(unique=True, editable=False, null=True, blank=True)


    # 🔹 User Type
    USER_TYPE_CHOICES = [
        ('guest', 'Guest'),
        ('devotee', 'Devotee'),
        ('mentor', 'Mentor'),   # ✅ New user type added
    ]
    user_type = models.CharField(max_length=20, choices=USER_TYPE_CHOICES, default='guest')

    # Basic Details
    username = models.CharField(max_length=100, blank=True, null=True)
    first_name = models.CharField(max_length=100, blank=True, null=True)
    last_name = models.CharField(max_length=100, blank=True, null=True)
    dob = models.DateField(blank=True, null=True)

    gender_choices = [
        ('male', 'Male'),
        ('female', 'Female'),
        ('other', 'Other'),
    ]
    gender = models.CharField(max_length=10, choices=gender_choices, blank=True, null=True)

    marital_status_choices = [
        ('sannyasi', 'Sannyasi'),
        ('grhastha', 'Grhastha'),
        ('others', 'Others'),
        ('unmarried', 'Unmarried'),
        ('vanaprastha', 'Vanaprastha'),
        ('brahmachari_temple', 'Brahmachari (Temple)'),
    ]
    marital_status = models.CharField(max_length=20, choices=marital_status_choices, blank=True, null=True)

    mobile = models.CharField(max_length=15, blank=True, null=True, unique=True)
    aadhar_card_no = models.CharField(max_length=12, blank=True, null=True, unique=True)
    country = models.CharField(max_length=100, blank=True, null=True)
    center = models.CharField(max_length=150, blank=True, null=True)

    # Initiation Details
    is_initiated = models.BooleanField(default=False)
    initiated_name = models.CharField(max_length=255, blank=True, null=True)
    spiritual_master = models.CharField(max_length=255, blank=True, null=True)
    initiation_date = models.DateField(blank=True, null=True)
    initiation_place = models.CharField(max_length=255, blank=True, null=True)

    # Communication Preferences
    email_consent = models.BooleanField(default=False)

    # Additional Information
    address = models.TextField(blank=True, null=True)
    emergency_contact = models.CharField(max_length=255, blank=True, null=True)
    mentor = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL)
    profile_picture = models.ImageField(upload_to=profile_picture_upload_path, blank=True, null=True)

    # 🔹 New Field — Number of Chanting Rounds
    no_of_chanting_rounds = models.PositiveIntegerField(default=0, help_text="Number of daily chanting rounds")

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.first_name or ''} {self.last_name or ''}".strip() or self.user.username

    def formatted_member_id(self):
        """Return member_id as 6-digit string (e.g., 000123)."""
        return f"{self.member_id:06d}"

    # def save(self, *args, **kwargs):
    #     if not self.member_id:
    #         with transaction.atomic():
    #             last_profile = Profile.objects.select_for_update().order_by('-member_id').first()
    #             next_id = (last_profile.member_id + 1) if last_profile else 1
    #             if next_id > 999999:
    #                 raise ValueError("Member ID limit reached (max 999999)")
    #             self.member_id = next_id
    #     super().save(*args, **kwargs)

    

class MentorRequest(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    from_user = models.ForeignKey('Profile', related_name='sent_requests', on_delete=models.CASCADE)
    to_mentor = models.ForeignKey('Profile', related_name='received_requests', on_delete=models.CASCADE)
    message = models.TextField(blank=True, null=True)
    is_approved = models.BooleanField(default=False)
    approved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.from_user} → {self.to_mentor}"
    
    def save(self, *args, **kwargs):
        if self.is_approved and self.approved_at is None:
            self.approved_at = timezone.now()
        super().save(*args, **kwargs)
    

