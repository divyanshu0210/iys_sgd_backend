from django.contrib import admin
from .models import *

# Register your models here.

class YatraFormFieldInline(admin.TabularInline):
    model = YatraFormField
    extra = 1
    fields = ['name', 'label', 'field_type', 'options', 'is_required', 'order']

class YatraInstallmentInline(admin.TabularInline):
    model = YatraInstallment
    extra = 1
    fields = ['label', 'amount', 'order']


@admin.register(Yatra)
class YatraAdmin(admin.ModelAdmin):
    list_display = ('id','title', 'location', 'start_date', 'end_date', 'capacity','payment_upi_id', 'created_at')
    search_fields = ('title', 'location')
    list_filter = ('start_date', 'location')
    ordering = ('-created_at',)
    inlines = [YatraFormFieldInline, YatraInstallmentInline]


# userProfile/admin.py (add this)

@admin.register(YatraEligibility)
class YatraEligibilityAdmin(admin.ModelAdmin):
    list_display = ('yatra', 'profile', 'approved_by', 'is_approved', 'approved_at')
    list_filter = ('is_approved', 'yatra','yatra__title', 'approved_at')
    search_fields = ('profile__first_name', 'profile__last_name', 'yatra__title')
    ordering = ('-approved_at',)

    def has_add_permission(self, request):
        return False

    # Optional: also hide from change/view pages of related models
    def has_module_permission(self, request):
        return True  # Still show in admin menu



@admin.register(YatraRegistration)
class YatraRegistrationAdmin(admin.ModelAdmin):
    list_display = (
        'yatra',
        'registered_for',
        'registered_by',
        'mentor_full_name',
        'status',
        'total_amount_display',
        'paid_amount_display',
        'installments_status',
        'registered_at',
    )
    search_fields = (
        'yatra__title',
        'registered_for__full_name',
        'registered_for__first_name',
        'registered_for__last_name',
        'registered_by__full_name',
    )
    list_filter = ('status','yatra__title', 'registered_at')
    ordering = ('-registered_at',)
    readonly_fields = ('total_amount_display', 'paid_amount_display', 'installments_status')

    # Clean display methods (no colors, no HTML)
    def total_amount_display(self, obj):
        return f"₹{obj.total_amount}"
    total_amount_display.short_description = "Total Amount"
    total_amount_display.admin_order_field = 'total_amount'

    def paid_amount_display(self, obj):
        return f"₹{obj.paid_amount}"
    paid_amount_display.short_description = "Paid"
    paid_amount_display.admin_order_field = 'paid_amount'

    # No admin_order_field here unless you add a custom annotation in get_queryset()
    def installments_status(self, obj):
        items = []
        for reg_inst in obj.installments.select_related('installment').order_by('installment__order'):
            label = reg_inst.installment.label if reg_inst.installment else "Unknown"
            status = "Paid" if reg_inst.is_paid else "Pending"
            items.append(f"{label} ({status})")
        return " • ".join(items) if items else "No installments defined"

    installments_status.short_description = "Installment Status"

    def mentor_full_name(self, obj):
        """Return mentor full name of the person who is registered_for."""
        if obj.registered_for and obj.registered_for.mentor:
            first = obj.registered_for.mentor.first_name or ""
            last = obj.registered_for.mentor.last_name or ""
            return f"{first} {last}".strip()
        return "-"
    mentor_full_name.short_description = "Mentor Name"

    def has_add_permission(self, request):
        return False

    # Optional: also hide from change/view pages of related models
    def has_module_permission(self, request):
        return True  # Still show in admin menu


# @admin.register(YatraRegistrationInstallment)
# class YatraRegistrationInstallmentAdmin(admin.ModelAdmin):
    
#     list_display = (
#         'registration', 
#         'installment', 
#         'payment',
#         'is_paid', 
#         'paid_at', 
#         'verified_by',
#         'verified_at'
#     )
#     list_filter = ('is_paid', 'paid_at', 'verified_at')
#     search_fields = (
#         'registration__registered_for__first_name',
#         'registration__registered_for__last_name',
#         'payment__transaction_id'
#     )
#     readonly_fields = ('paid_at',)

#     def uploaded_at(self, obj):
#         return obj.payment.uploaded_at if obj.payment else None
#     uploaded_at.short_description = "Uploaded At"