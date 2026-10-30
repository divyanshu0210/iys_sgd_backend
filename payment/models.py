from django.db import models
import uuid
from userProfile.models import *
from yatra.models import *
from django.utils import timezone
from django.db import transaction
from payment.notifications import notify_payment_result


# models.py - Add Payment model to track single transactions

class Donation(models.Model):
    """Donation and its payment screenshot."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    donor_name = models.CharField(max_length=255)
    initiated_name = models.CharField(max_length=255, blank=True)
    address = models.TextField()
    mobile = models.CharField(max_length=30)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    pan = models.CharField(max_length=32, blank=True)
    email = models.EmailField()
    transaction_id = models.CharField(max_length=100, unique=True)
    screenshot = models.ImageField(upload_to="donation_proofs/")
    status = models.CharField(
        max_length=20,
        choices=[("under_review", "Under review"), ("verified", "Verified"), ("rejected", "Rejected")],
        default="under_review",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.donor_name} — {self.transaction_id}"


class Payment(models.Model):
    """
    Track a single payment transaction that can cover multiple installments
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    transaction_id = models.CharField(max_length=255, unique=True)
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    proof = models.FileField(upload_to='payment_proofs/')
    uploaded_by = models.ForeignKey(Profile, on_delete=models.CASCADE)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    PAYMENT_STATUS = [
        ("pending", "Pending"),
        ("verified", "Verified"),
        ("rejected", "Rejected"),
        ("under_review", "Under Review"),
        ("refunded", "Refunded"),
    ]

    # Verification fields
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS, default="under_review")

    # is_verified = models.BooleanField(default=False)
    processed_by  = models.ForeignKey(
        Profile, 
        null=True, 
        blank=True, 
        related_name='processed_payments', 
        on_delete=models.SET_NULL
    )
    processed_at  = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Payment {self.transaction_id} - ₹{self.total_amount}"
    
    def approve(self, user_profile, notes=""):
        was_verified = self.status == "verified"
        self.status = "verified"
        self.processed_by = user_profile
        self.processed_at = timezone.now()
        self.notes = notes
        self.save()

        # mark installments as paid
        for inst in self.installments.all():
            inst.is_paid = True
            inst.paid_at = timezone.now()
            inst.verified_by = user_profile
            inst.verified_at = timezone.now()
            inst.save()
            inst.registration.update_status()
        if not was_verified:
            transaction.on_commit(lambda: notify_payment_result(self, True, user_profile))

    def reject(self, user_profile, notes=""):
        was_rejected = self.status == "rejected"
        self.status = "rejected"
        self.processed_by = user_profile
        self.processed_at = timezone.now()
        self.notes = notes
        self.save()

        # rollback installments
        for inst in self.installments.all():
            inst.is_paid = False
            inst.paid_at = None
            inst.verified_by = user_profile
            inst.verified_at = timezone.now()
            inst.save()
            inst.registration.update_status()
        if not was_rejected:
            transaction.on_commit(lambda: notify_payment_result(self, False, user_profile))

    def mark_under_review(self, user_profile, notes=""):
        self.status = "under_review"
        self.processed_by = None
        self.processed_at = None
        self.notes = notes
        self.save()

        for inst in self.installments.all():
            inst.is_paid = False
            inst.verified_by = None
            inst.verified_at = None
            inst.save()
            inst.registration.update_status()
        
    
    def has_add_permission(self, request):
        return False

    # Optional: also hide from change/view pages of related models
    def has_module_permission(self, request):
        return True  # Still show in admin menu
