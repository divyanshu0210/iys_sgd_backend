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
    is_registration_open = models.BooleanField(default=True) 
    is_rcs_download_open = models.BooleanField(default=False) 
    is_substitution_open = models.BooleanField(default=False) 
    payment_upi_id = models.CharField(max_length=255, blank=True, null=True,default="")  
    substitution_fee = models.DecimalField(max_digits=10, decimal_places=2, default=500)
    cancellation_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
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



# === 1. Yatra Journey (multiple travel segments) ===
class YatraJourney(models.Model):
    JOURNEY_TYPES = [
        ('onward', 'Onward'),
        ('return', 'Return'),
        ('break', 'Break'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    yatra = models.ForeignKey('Yatra', related_name='journeys', on_delete=models.CASCADE)
    type = models.CharField(max_length=20, choices=JOURNEY_TYPES)
    from_location = models.CharField(max_length=255)
    to_location = models.CharField(max_length=255)
    start_datetime = models.DateTimeField()
    end_datetime = models.DateTimeField()   
    mode_of_travel = models.CharField(max_length=50, blank=True, null=True)
    remarks = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['start_datetime']

    def __str__(self):
        return f"{self.yatra.title} → {self.type} ({self.from_location} → {self.to_location})"



# === 2. Yatra Accommodation (can have multiple per yatra) ===
class YatraAccommodation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    yatra = models.ForeignKey('Yatra', related_name='accommodations', on_delete=models.CASCADE)
    place_name = models.CharField(max_length=255)
    address = models.TextField(blank=True, null=True)
    checkin_datetime = models.DateTimeField()
    checkout_datetime = models.DateTimeField()
    contact_person = models.CharField(max_length=255, blank=True, null=True)
    contact_number = models.CharField(max_length=50, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['checkin_datetime']

    def __str__(self):
        return f"{self.yatra.title} → {self.place_name}"



class YatraCustomField(models.Model):
    FIELD_TYPES = [
        ('text', 'Text'),
        ('number', 'Number'),
        ('date', 'Date'),
        ('datetime', 'Datetime'),
        ('choice', 'Choice'),
        ('file', 'File'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    yatra = models.ForeignKey('Yatra', related_name='custom_fields', on_delete=models.CASCADE)
    field_name = models.CharField(max_length=255)
    field_type = models.CharField(max_length=20, choices=FIELD_TYPES, default='text')
    is_multiple = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['order', 'field_name']

    def __str__(self):
        return f"{self.yatra.title} → {self.field_name}"



class YatraCustomFieldValue(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    custom_field = models.ForeignKey(YatraCustomField, related_name='values', on_delete=models.CASCADE)
    value = models.TextField()

    class Meta:
        verbose_name = "Custom Field Value"
        verbose_name_plural = "Custom Field Values"

    def __str__(self):
        return f"{self.custom_field.field_name} → {self.value}"
