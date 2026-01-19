from django.db import models
import uuid
from userProfile.models import Profile
from payment.models import Payment
from django.core.exceptions import ValidationError
from yatra.models import *
from django.utils import timezone

    
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
    yatra = models.ForeignKey(Yatra, on_delete=models.CASCADE)
    registered_by = models.ForeignKey(Profile, related_name='registrations_made', on_delete=models.CASCADE)
    registered_for = models.ForeignKey(Profile, related_name='registrations_received', on_delete=models.CASCADE)
    status = models.CharField(
        max_length=20, 
        choices=[
            ('pending', 'Not Started'),
            ('partial', 'Incomplete'),
            ('paid', 'Confirmed'),
            ('substituted', 'Substituted '),
            ('refunded', 'Refunded'),
            ('cancelled', 'Cancelled'),
            ('attended', 'Attended'),
        ],
        default='pending'
    )
    form_data = models.JSONField(default=dict, blank=True)
    registered_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    #the following fields are for substitution and cancellation tracking
    substituted_to = models.ForeignKey(Profile, null=True, blank=True, on_delete=models.SET_NULL, related_name="substituted_from")
    substitution_date = models.DateTimeField(null=True, blank=True)
    cancellation_date = models.DateTimeField(null=True, blank=True)


    class Meta:
        unique_together = ('yatra', 'registered_for')
        indexes = [
            models.Index(fields=['registered_at']),
            models.Index(fields=['status']),
            models.Index(fields=['yatra']),
            models.Index(fields=['registered_for']),
        ]

    # def __str__(self):
    #     return f"{self.registered_for} - {self.yatra.title}"
    def __str__(self):
        return f"Registration {self.id}"


    @property
    def total_amount(self):
        """Total amount for all installments of this yatra"""
        return sum(inst.amount for inst in self.yatra.installments.all())

    @property
    def paid_amount(self):
        """Sum of all verified payments"""
        return sum(
            inst.installment.amount for inst in self.installments.filter(is_paid=True)
        )
    
    def has_any_installment_under_verification(self):
        return self.installments.filter(
            payment__isnull=False,
            is_paid=False
        ).exists()

    @property
    def pending_amount(self):
        return self.total_amount - self.paid_amount

    def update_status(self):
        """Update registration status based on payments"""
        total_installments = self.yatra.installments.count()

        paid_installments = self.installments.filter(is_paid=True).count()
        initiated_installments = self.installments.filter(payment__isnull=False).count()
        if initiated_installments == 0:
            self.status = 'pending'
        elif paid_installments == total_installments:
            self.status = 'paid'
        else:
            self.status = 'partial'
        self.save()


class YatraRegistrationInstallment(models.Model):
    """
    Track installment payments for each registration
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    registration = models.ForeignKey(
        YatraRegistration,
        related_name='installments',
        on_delete=models.CASCADE
    )
    installment = models.ForeignKey(YatraInstallment, on_delete=models.CASCADE,null=True, blank=True)
    is_paid = models.BooleanField(default=False)
    paid_at = models.DateTimeField(null=True, blank=True)
    
    # Link to the main payment
    payment = models.ForeignKey(
        Payment, 
        related_name='installments',
        null=True,
        blank=True,
        on_delete=models.SET_NULL
    )
    
    # Verification metadata
    verified_by = models.ForeignKey(
        Profile, 
        null=True, 
        blank=True, 
        related_name='verified_installments', 
        on_delete=models.SET_NULL
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        unique_together = ('registration', 'installment')

    def __str__(self):
        return f"{self.registration} - {self.installment.label} ({'Paid' if self.is_paid else 'Pending'})"



# === 5. Registration-specific accommodations / journeys / custom values ===
# === Registration-specific Accommodation Assignment ===
class RegistrationAccommodation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    registration = models.ForeignKey('YatraRegistration', related_name='accommodation_allocations', on_delete=models.CASCADE)
    accommodation = models.ForeignKey(YatraAccommodation, on_delete=models.CASCADE)
    room_number = models.CharField(max_length=50, blank=True, null=True)
    bed_number = models.CharField(max_length=50, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        unique_together = ('registration', 'accommodation')

    def __str__(self):
        return f"{self.registration.registered_for} → {self.accommodation.place_name} (Room {self.room_number})"

# === Registration-specific Journey Assignment ===
class RegistrationJourney(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    registration = models.ForeignKey('YatraRegistration', related_name='journey_allocations', on_delete=models.CASCADE)
    journey = models.ForeignKey(YatraJourney, on_delete=models.CASCADE)
    vehicle_number = models.CharField(max_length=50, blank=True, null=True)
    seat_number = models.CharField(max_length=50, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        unique_together = ('registration', 'journey')

    def __str__(self):
        return f"{self.registration.registered_for} → {self.journey.type} ({self.seat_number or 'No Seat'})"

class RegistrationCustomFieldValue(models.Model):
    registration = models.ForeignKey(
        'YatraRegistration', related_name='custom_values', on_delete=models.CASCADE
    )
    custom_field = models.ForeignKey(
        YatraCustomField, on_delete=models.CASCADE , null=True, blank=True
    )
    custom_field_value = models.ForeignKey(
        YatraCustomFieldValue, on_delete=models.CASCADE
    )

    class Meta:
        unique_together = ('registration', 'custom_field')

class RCSDownloadEvent(models.Model):
    registration = models.OneToOneField(
        "YatraRegistration",
        on_delete=models.CASCADE,
        related_name="rcs_download_event"
    )
    count = models.PositiveIntegerField(default=0)
    timestamps = models.JSONField(default=list, blank=True)
    last_downloaded_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["registration"]),
            models.Index(fields=["last_downloaded_at"]),
        ]

    def record_download(self):
        now = timezone.now()
        self.count += 1
        self.timestamps.append(now.isoformat())
        self.last_downloaded_at = now
        self.save(update_fields=["count", "timestamps", "last_downloaded_at"])

    def __str__(self):
        return f"RCS downloads: {self.count} for {self.registration_id}"