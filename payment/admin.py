from django.contrib import admin
from pathlib import PurePosixPath
from django.utils.html import format_html
from .models import *
from yatra.admin_utils import ActiveYatraAdminMixin
from userProfile.admin_utils import format_profile_name


def _proof_preview(proof):
    """Render the same safe, hoverable proof link for both admin lists."""
    if not proof:
        return '—'
    url = proof.url
    name = PurePosixPath(proof.name).name
    if PurePosixPath(name).suffix.lower() not in {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp', '.avif'}:
        return format_html('<a href="{}" target="_blank" rel="noopener noreferrer">{}</a>', url, name)
    return format_html(
        '<span class="payment-proof-preview"><a href="{}" target="_blank" rel="noopener noreferrer">{}</a>'
        '<span class="payment-proof-preview__image"><img src="{}" alt="Payment proof preview" loading="lazy"></span></span>',
        url, name, url,
    )


@admin.register(Donation)
class DonationAdmin(admin.ModelAdmin):
    class Media:
        css = {'all': ('payment/css/proof_preview.css',)}

    list_display = ("transaction_id", "amount", "proof_preview", "donor_name", "email", "status", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("donor_name", "email", "mobile", "transaction_id")
    readonly_fields = ("created_at",)
    ordering = ("-created_at",)

    @admin.display(description='Proof')
    def proof_preview(self, obj):
        return _proof_preview(obj.screenshot)

    def has_add_permission(self, request):
        return False


@admin.register(Payment)
class PaymentAdmin(ActiveYatraAdminMixin, admin.ModelAdmin):
    class Media:
        css = {'all': ('payment/css/proof_preview.css',)}

    admin_yatra_lookup = 'installments__registration__yatra'
    change_list_template = "admin/active_yatra_changelist.html"

    def has_add_permission(self, request):
        return False

    list_display = (
        'transaction_id', 
        'total_amount', 
        'proof_preview',
        'uploaded_by_display',
        'status',
        'processed_at',
        # 'uploaded_at',
        # 'is_verified',
        # 'verified_at'
    )
    list_filter = ('uploaded_at', 'processed_at', 'status')
    search_fields = ('transaction_id', 'uploaded_by__first_name', 'uploaded_by__last_name', 'uploaded_by__initiated_name')
    list_select_related = ('uploaded_by',)
    readonly_fields = ('uploaded_at',)
    actions = ["approve_selected", "reject_selected","under_review"]

    @admin.display(description='Proof')
    def proof_preview(self, obj):
        return _proof_preview(obj.proof)

    @admin.display(description='Uploaded by', ordering='uploaded_by__first_name')
    def uploaded_by_display(self, obj):
        return format_profile_name(obj.uploaded_by)

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
