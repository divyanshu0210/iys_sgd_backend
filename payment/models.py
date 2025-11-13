from django.db import models
import uuid
from userProfile.models import *
from yatra.models import *
from django.utils import timezone


# models.py - Add Payment model to track single transactions

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
    
    # Verification fields
    is_verified = models.BooleanField(default=False)
    verified_by = models.ForeignKey(
        Profile, 
        null=True, 
        blank=True, 
        related_name='verified_payments', 
        on_delete=models.SET_NULL
    )
    verified_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Payment {self.transaction_id} - ₹{self.total_amount}"

    def mark_verified(self, verifier_profile, notes=""):
        if not self.is_verified:
            self.is_verified = True
            self.verified_by = verifier_profile
            self.verified_at = timezone.now()
            self.notes = notes
            self.save()
            
            # Mark all associated installments as paid
            for installment in self.installments.all():
                installment.is_paid = True
                installment.paid_at = timezone.now() # type: ignore
                installment.verified_by = verifier_profile
                installment.verified_at = timezone.now()
                installment.save()
                installment.registration.update_status()
