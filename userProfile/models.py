from django.db import models, transaction
import uuid
from django.contrib.auth.models import User
import os
import uuid
from django.db import models
# models.py



class Yatra(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    description = models.TextField()
    start_date = models.DateField()
    end_date = models.DateField()
    location = models.CharField(max_length=255)
    capacity = models.IntegerField()
    is_registration_open = models.BooleanField(default=True)  # ✅ New field
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title

class YatraFormField(models.Model):
    FIELD_TYPES = [
        ('text', 'Text'),
        ('select', 'Dropdown'),
        ('radio', 'Radio Buttons'),
        ('checkbox', 'Checkbox'),
        ('number', 'Number'),
        ('date', 'Date'),
    ]

    yatra = models.ForeignKey(Yatra, on_delete=models.CASCADE, related_name='form_fields')
    name = models.CharField(max_length=100, help_text="Internal field name (e.g., accommodation)")
    label = models.CharField(max_length=200, help_text="Label shown to user")
    field_type = models.CharField(max_length=20, choices=FIELD_TYPES, default='text')
    options = models.TextField(
        blank=True,
        help_text="Comma-separated options for select/radio (e.g., Dorm,Shared,Private)"
    )
    is_required = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']

    def clean(self):
        if self.field_type in ['select', 'radio'] and not self.options.strip():
            raise ValidationError(f"{self.label}: Options are required for {self.field_type}")

    def __str__(self):
        return f"{self.yatra.title} → {self.label}"

    def get_options_list(self):
        return [opt.strip() for opt in self.options.split(',') if opt.strip()]


# === 2. Payment Installment Options ===
class YatraInstallment(models.Model):
    yatra = models.ForeignKey(Yatra, on_delete=models.CASCADE, related_name='installments')
    label = models.CharField(max_length=100, help_text="e.g., Full Payment (₹6500)")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'id']
        unique_together = ('yatra', 'label')

    def __str__(self):
        return f"{self.yatra.title} → {self.label} (₹{self.amount})"


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
    member_id = models.PositiveIntegerField(unique=True, editable=False)

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

    mobile = models.CharField(max_length=15, blank=True, null=True)
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

    def save(self, *args, **kwargs):
        if not self.member_id:
            with transaction.atomic():
                last_profile = Profile.objects.select_for_update().order_by('-member_id').first()
                next_id = (last_profile.member_id + 1) if last_profile else 1
                if next_id > 999999:
                    raise ValueError("Member ID limit reached (max 999999)")
                self.member_id = next_id
        super().save(*args, **kwargs)

    





# class YatraRegistration(models.Model):
#     id = models.UUIDField(primary_key=True, default=uuid.uuid4)
#     yatra = models.ForeignKey(Yatra, on_delete=models.CASCADE)
#     registrant = models.ForeignKey(Profile, related_name='registrations_made', on_delete=models.CASCADE)
#     registered_for = models.ForeignKey(Profile, related_name='registrations_received', on_delete=models.CASCADE)
#     status = models.CharField(max_length=20, default='pending')
#     registered_at = models.DateTimeField(auto_now_add=True)

#     class Meta:
#         unique_together = ('yatra', 'registered_for')

# userProfile/models.py (add this new model)

class YatraEligibility(models.Model):
    """
    Tracks whether a profile (devotee) is approved by their mentor for a specific Yatra.
    Only approved profiles can be registered for that Yatra.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    yatra = models.ForeignKey(Yatra, on_delete=models.CASCADE, related_name='eligibility_approvals')
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='yatra_eligibilities')
    approved_by = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name='yatra_approvals_given')  # The mentor who approved
    is_approved = models.BooleanField(default=False)
    approved_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('yatra', 'profile')  # One approval per profile per Yatra
        verbose_name_plural = "Yatra Eligibilities"

    def __str__(self):
        return f"{self.profile} - {self.yatra.title} ({'Approved' if self.is_approved else 'Pending'})"




class YatraRegistration(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    yatra = models.ForeignKey('Yatra', on_delete=models.CASCADE)
    registered_for = models.ForeignKey('Profile', on_delete=models.CASCADE)
    registered_by = models.ForeignKey(User, on_delete=models.CASCADE)
    registration_data = models.JSONField()
    installment_label = models.CharField(max_length=200)
    amount_due = models.DecimalField(max_digits=10, decimal_places=2)  # e.g., 3000
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    # Status
    is_payment_verified = models.BooleanField(default=False)
    payment_status = models.CharField(
        max_length=50,
        choices=[
            ('pending', 'Pending'),
            ('partial', 'Partial (1st Verified)'),
            ('full', 'Full Payment Verified'),
        ],
        default='pending'
    )
    registration_status = models.CharField(
        max_length=50,
        choices=[
            ('pending', 'Pending'),
            ('confirmed', 'Confirmed'),
        ],
        default='pending'
    )

    def __str__(self):
        return f"{self.registered_for} → {self.yatra}"

class BatchPaymentProof(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    transaction_id = models.CharField(max_length=100)
    screenshot = models.ImageField(upload_to='batch_screenshots/')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    paid_at = models.DateTimeField(auto_now_add=True)

    # FIX: Avoid reverse accessor clash
    submitted_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='submitted_payments'  # Unique!
    )
    is_verified = models.BooleanField(default=False)
    verified_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='verified_payments'  # Unique!
    )
    verified_at = models.DateTimeField(null=True, blank=True)

    registrations = models.ManyToManyField(
        'YatraRegistration',
        through='BatchPaymentAllocation',
        related_name='batch_payments'
    )

    def __str__(self):
        return f"Batch ₹{self.total_amount} – {self.transaction_id}"

class BatchPaymentAllocation(models.Model):
    batch_proof = models.ForeignKey(BatchPaymentProof, on_delete=models.CASCADE)
    registration = models.ForeignKey(YatraRegistration, on_delete=models.CASCADE)
    amount_allocated = models.DecimalField(max_digits=10, decimal_places=2)


class MentorRequest(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    from_user = models.ForeignKey('Profile', related_name='sent_requests', on_delete=models.CASCADE)
    to_mentor = models.ForeignKey('Profile', related_name='received_requests', on_delete=models.CASCADE)
    message = models.TextField(blank=True, null=True)
    is_approved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.from_user} → {self.to_mentor}"
    