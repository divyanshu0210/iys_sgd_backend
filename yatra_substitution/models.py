from django.db import models

from yatra_registration.models import *
from userProfile.models import *

# Create your models here.

class SubstitutionRequest(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("accepted", "Accepted"),
        ("rejected", "Rejected"),
        ("cancelled", "Cancelled"), #lets keep but we will not provide any api to set this
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    registration = models.ForeignKey(YatraRegistration, on_delete=models.CASCADE, related_name="substitution_requests")
    initiator = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="substitution_sent")
    target_profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="substitution_received")
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="pending")
    two_digit_code = models.CharField(max_length=4)  # stored server-side (can be hashed for extra safety)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    note = models.TextField(blank=True, default="")  # optional note
    amount_paid = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    processed_by = models.ForeignKey(Profile, null=True, blank=True, on_delete=models.SET_NULL) #it wont be processed by admin but by themselves
    fee_collected = models.BooleanField(default=False)
    new_registration = models.ForeignKey(YatraRegistration, on_delete=models.CASCADE, related_name="new_reg",null=True, blank=True)


    class Meta:
        indexes = [
            models.Index(fields=["target_profile", "status"]),
        ]