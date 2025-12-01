from django.db import models
import uuid
from userProfile.models import Profile
from payment.models import Payment
from django.core.exceptions import ValidationError



class Yatra(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    description = models.TextField()
    start_date = models.DateField()
    end_date = models.DateField()
    location = models.CharField(max_length=255)
    capacity = models.IntegerField()
    is_registration_open = models.BooleanField(default=True)  # ✅ New field
    payment_upi_id = models.CharField(max_length=255, blank=True, null=True,default="")  # ✅ New field for UPI ID
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
            raise ValidationError(f"{self.label}: Options are required for {self.field_type}") # type: ignore

    def __str__(self):
        return f"{self.yatra.title} → {self.label}"

    def get_options_list(self):
        return [opt.strip() for opt in self.options.split(',') if opt.strip()]


    
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
            ('cancelled', 'Cancelled')
        ],
        default='pending'
    )
    form_data = models.JSONField(default=dict, blank=True)
    registered_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('yatra', 'registered_for')

    def __str__(self):
        return f"{self.registered_for} - {self.yatra.title}"

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

