from django.contrib import admin
from .models import *


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        'transaction_id', 
        'total_amount', 
        'proof',
        'uploaded_by', 
        'uploaded_at',
        'is_verified',
        'verified_at'
    )
    list_filter = ('is_verified', 'uploaded_at', 'verified_at')
    search_fields = ('transaction_id', 'uploaded_by__first_name', 'uploaded_by__last_name')
    readonly_fields = ('uploaded_at',)
    actions = ['verify_payments', 'unverify_payments']

    def verify_payments(self, request, queryset):
        for payment in queryset:
            payment.mark_verified(request.user.profile, "Bulk verification via admin")
        self.message_user(request, f"{queryset.count()} payments verified.")
    verify_payments.short_description = "Verify selected payments"

    def unverify_payments(self, request, queryset):
        updated = 0
        for payment in queryset:
            if payment.is_verified:
                payment.is_verified = False
                payment.verified_by = None
                payment.verified_at = None
                payment.save()
                
                # Also unverify all linked installments
                for installment in payment.installments.all():
                    installment.is_paid = False
                    installment.paid_at = None
                    installment.verified_by = None
                    installment.verified_at = None
                    installment.save()
                    installment.registration.update_status()
                
                updated += 1
        self.message_user(request, f"{updated} payments unverified.")
    unverify_payments.short_description = "Unverify selected payments"
