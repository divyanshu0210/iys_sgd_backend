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
    list_filter = ('is_approved', 'yatra', 'approved_at')
    search_fields = ('profile__first_name', 'profile__last_name', 'yatra__title')
    ordering = ('-approved_at',)


@admin.register(YatraRegistration)
class YatraRegistrationAdmin(admin.ModelAdmin):
    list_display = ('yatra', 'registered_for', 'registered_by', 'status', 'registered_at','updated_at')
    search_fields = ('yatra__title', 'registered_for__full_name', 'registered_by__full_name')
    list_filter = ('status', 'yatra')
    ordering = ('-registered_at',)

@admin.register(YatraRegistrationInstallment)
class YatraRegistrationInstallmentAdmin(admin.ModelAdmin):
    
    list_display = (
        'registration', 
        'installment', 
        'payment',
        'is_paid', 
        'paid_at', 
        'verified_by',
        'verified_at'
    )
    list_filter = ('is_paid', 'paid_at', 'verified_at')
    search_fields = (
        'registration__registered_for__first_name',
        'registration__registered_for__last_name',
        'payment__transaction_id'
    )
    readonly_fields = ('paid_at',)

    def uploaded_at(self, obj):
        return obj.payment.uploaded_at if obj.payment else None
    uploaded_at.short_description = "Uploaded At"