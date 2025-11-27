from django.contrib import admin
from .models import *


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = (
        'transaction_id', 
        'total_amount', 
        'proof',
        'uploaded_by', 
        'status',
        'processed_at',
        # 'uploaded_at',
        # 'is_verified',
        # 'verified_at'
    )
    list_filter = ('uploaded_at', 'processed_at', 'status')
    search_fields = ('transaction_id', 'uploaded_by__first_name', 'uploaded_by__last_name')
    readonly_fields = ('uploaded_at',)
    # actions = ['verify_payments', 'unverify_payments']
    actions = ["approve_selected", "reject_selected","under_review"]

    def approve_selected(self, request, queryset):
        for p in queryset:
            p.approve(request.user.profile, "Verified via admin panel")
        self.message_user(request, f"{queryset.count()} payments verified.")
    approve_selected.short_description = "Approve selected payments"

    def reject_selected(self, request, queryset):
        for p in queryset:
            p.reject(request.user.profile, "Rejected via admin panel")
        self.message_user(request, f"{queryset.count()} payments rejected.")
    reject_selected.short_description = "Reject selected payments"
    
    def under_review(self, request, queryset):
        for p in queryset:
            p.mark_under_review(request.user.profile, "Marked under review via admin panel")
        self.message_user(request, f"{queryset.count()} payments marked under review.")
    under_review.short_description = "Mark selected payments as under review"

    # def verify_payments(self, request, queryset):
    #     for payment in queryset:
    #         payment.mark_verified(request.user.profile, "Bulk verification via admin")
    #     self.message_user(request, f"{queryset.count()} payments verified.")
    # verify_payments.short_description = "Verify selected payments"

    # def unverify_payments(self, request, queryset):
    #     updated = 0
    #     for payment in queryset:
    #         if payment.is_verified:
    #             payment.is_verified = False
    #             payment.verified_by = None
    #             payment.verified_at = None
    #             payment.save()
                
    #             # Also unverify all linked installments
    #             for installment in payment.installments.all():
    #                 installment.is_paid = False
    #                 installment.paid_at = None
    #                 installment.verified_by = None
    #                 installment.verified_at = None
    #                 installment.save()
    #                 installment.registration.update_status()
                
    #             updated += 1
    #     self.message_user(request, f"{updated} payments unverified.")
    # unverify_payments.short_description = "Unverify selected payments"
