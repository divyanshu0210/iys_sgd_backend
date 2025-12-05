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

