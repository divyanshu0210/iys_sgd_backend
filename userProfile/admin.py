from django.contrib import admin

from .models import *
from django.contrib import admin
from django.utils.html import format_html

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
    list_display = ('title', 'location', 'start_date', 'end_date', 'capacity', 'created_at')
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


from django.contrib import admin
from .models import Profile


from django.contrib import admin
from .models import Profile

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = (
        'formatted_member_id',
        'user',
        'user_type',
        'first_name',
        'last_name',
        'mobile',
        'aadhar_card_no',
        'country',
        'center',
        'is_initiated',
        'spiritual_master',
        'no_of_chanting_rounds',  # ✅ Display in admin list
        'created_at',
    )

    search_fields = (
        'member_id',
        'first_name',
        'last_name',
        'mobile',
        'aadhar_card_no',
        'country',
        'center',
        'spiritual_master',
    )

    list_filter = (
        'user_type',
        'gender',
        'marital_status',
        'country',
        'center',
        'is_initiated',
        'spiritual_master',
    )

    readonly_fields = ('member_id', 'created_at')
    ordering = ('-created_at',)

    def save_model(self, request, obj, form, change):
        """
        Auto-create MentorRequest when mentor is assigned in Admin
        """
        old_mentor = None
        if change:
            try:
                old = Profile.objects.get(pk=obj.pk)
                old_mentor = old.mentor
            except Profile.DoesNotExist:
                pass

        super().save_model(request, obj, form, change)

        # Only trigger if mentor was changed AND user is superuser
        if request.user.is_superuser and obj.mentor and (not change or old_mentor != obj.mentor):
            # Auto-create approved MentorRequest
            MentorRequest.objects.update_or_create(
                from_user=obj,
                to_mentor=obj.mentor,
                defaults={
                    'is_approved': True,
                    'message': 'Auto-approved by superuser assignment in admin',
                }
            )

    def formatted_member_id(self, obj):
        return f"{obj.member_id:06d}"
    formatted_member_id.short_description = "Member ID"




@admin.register(YatraRegistration)
class YatraRegistrationAdmin(admin.ModelAdmin):
    list_display = ('yatra', 'registered_for', 'registered_by', 'payment_status','registration_status', 'created_at')
    search_fields = ('yatra__title', 'registered_for__full_name', 'registered_by__full_name')
    list_filter = ('payment_status','registration_status', 'yatra')
    ordering = ('-created_at',)


# ✅ NEW: Mentor Request Admin
@admin.register(MentorRequest)
class MentorRequestAdmin(admin.ModelAdmin):
    list_display = ('id','from_user', 'to_mentor', 'is_approved', 'created_at')
    search_fields = (
        'from_user__first_name',
        'to_mentor__first_name',
        'from_user__member_id',
        'to_mentor__member_id',
    )
    list_filter = ('is_approved', 'created_at')
    ordering = ('-created_at',)


# admin.py
from django.contrib import admin
from django.utils import timezone
from .models import (
    YatraRegistration,
    BatchPaymentProof,
    BatchPaymentAllocation
)

@admin.register(BatchPaymentProof)
class BatchPaymentProofAdmin(admin.ModelAdmin):
    list_display = [
        'transaction_id',
        'total_amount',
        'submitted_by',
        'registration_count',   # Custom count method
        'is_verified',
        'verified_by',
        'verified_at',
        'view_screenshot',
    ]
    list_filter = ['is_verified', 'paid_at', 'submitted_by']
    search_fields = ['transaction_id', 'submitted_by__username']
    readonly_fields = ['paid_at', 'verified_at', 'screenshot']
    actions = ['verify_batch']

    def registration_count(self, obj):
        return obj.registrations.count()  # Uses the reverse relation
    registration_count.short_description = "Devotees"

    def view_screenshot(self, obj):
        if obj.screenshot:
            return format_html(
                '<a href="{}" target="_blank">View Screenshot</a>',
                obj.screenshot.url
            )
        return "-"
    view_screenshot.short_description = "Screenshot"

    def total_amount(self, obj):
        # Sum allocated amounts
        total = obj.batchpaymentallocation_set.aggregate(
            total=models.Sum('amount_allocated')
        )['total'] or 0
        return f"₹{total}"
    total_amount.short_description = "Total Amount"

    def verify_batch(self, request, queryset):
        from django.utils import timezone
        now = timezone.now()
        updated = 0

        for batch in queryset.filter(is_verified=False):
            batch.is_verified = True
            batch.verified_by = request.user
            batch.verified_at = now
            batch.save()

            # Update each registration via allocations
            for alloc in batch.batchpaymentallocation_set.select_related('registration'):
                reg = alloc.registration
                reg.amount_paid += alloc.amount_allocated

                if reg.amount_paid >= reg.amount_due:
                    reg.payment_status = 'full'
                    reg.registration_status = 'confirmed'
                elif reg.amount_paid > 0:
                    reg.payment_status = 'partial'
                else:
                    reg.payment_status = 'pending'
                reg.save()

            updated += 1

        self.message_user(request, f"{updated} batch(es) verified successfully.")
    verify_batch.short_description = "Verify selected batch payments"
    list_display = [
        'transaction_id',
        'total_amount',
        'submitted_by',
        'is_verified',
        'verified_by',
        'verified_at',
        'devotee_count',  # Custom method
        'view_screenshot',  # Custom column
    ]
    list_filter = [
        'is_verified',
        'paid_at',
        'submitted_by',
    ]
    search_fields = ['transaction_id', 'submitted_by__username']
    readonly_fields = ['paid_at', 'verified_at', 'screenshot']
    actions = ['verify_batch']

    # Custom column: number of devotees
    def devotee_count(self, obj):
        return obj.batchpaymentallocation_set.count()
    devotee_count.short_description = "Devotees"

    # Custom column: view screenshot
    def view_screenshot(self, obj):
        if obj.screenshot:
            return format_html(
                '<a href="{}" target="_blank">View SS</a>',
                obj.screenshot.url
            )
        return "-"
    view_screenshot.short_description = "Screenshot"

    # Action: Verify batch
    def verify_batch(self, request, queryset):
        now = timezone.now()
        updated = 0

        for batch in queryset.filter(is_verified=False):
            batch.is_verified = True
            batch.verified_by = request.user
            batch.verified_at = now
            batch.save()

            # Update each registration
            for alloc in batch.batchpaymentallocation_set.select_related('registration'):
                reg = alloc.registration
                reg.amount_paid += alloc.amount_allocated

                if reg.amount_paid >= reg.amount_due:
                    reg.payment_status = 'full'
                    reg.registration_status = 'confirmed'
                elif reg.amount_paid > 0:
                    reg.payment_status = 'partial'
                else:
                    reg.payment_status = 'pending'
                reg.save()

            updated += 1

        self.message_user(request, f"{updated} batch(es) verified successfully.")
    verify_batch.short_description = "Verify selected batch payments"
    list_display = [
        'transaction_id',
        'total_amount',
        'submitted_by',
        'is_verified',
        'verified_by',
        'verified_at',
        'registration_count'  # Custom method
    ]
    list_filter = [
        'is_verified',
        'paid_at',
        'submitted_by',
    ]
    search_fields = ['transaction_id', 'submitted_by__username']
    readonly_fields = ['paid_at', 'verified_at']
    actions = ['verify_batch']

    def registration_count(self, obj):
        return obj.batchpaymentallocation_set.count()
    registration_count.short_description = "Devotees"

    def verify_batch(self, request, queryset):
        now = timezone.now()
        updated = 0
        for batch in queryset.filter(is_verified=False):
            batch.is_verified = True
            batch.verified_by = request.user
            batch.verified_at = now
            batch.save()

            # Update each registration
            for alloc in batch.batchpaymentallocation_set.select_related('registration'):
                reg = alloc.registration
                reg.amount_paid += alloc.amount_allocated

                if reg.amount_paid >= reg.amount_due:
                    reg.payment_status = 'full'
                    reg.registration_status = 'confirmed'
                elif reg.amount_paid > 0:
                    reg.payment_status = 'partial'
                else:
                    reg.payment_status = 'pending'
                reg.save()

            updated += 1

        self.message_user(request, f"{updated} batch(es) verified successfully.")
    verify_batch.short_description = "Verify selected batch payments"
    list_display = ['transaction_id', 'total_amount', 'submitted_by', 'is_verified']
    actions = ['verify_batch']

    def verify_batch(self, request, queryset):
        for batch in queryset:
            if batch.is_verified:
                continue

            batch.is_verified = True
            batch.verified_by = request.user
            batch.verified_at = now()
            batch.save()

            # Update each registration
            for alloc in batch.batchpaymentallocation_set.all():
                reg = alloc.registration
                reg.amount_paid += alloc.amount_allocated

                # Update status
                if reg.amount_paid >= reg.amount_due:
                    reg.payment_status = 'full'
                    reg.registration_status = 'confirmed'
                elif reg.amount_paid > 0:
                    reg.payment_status = 'partial'
                reg.save()

        self.message_user(request, f"{queryset.count()} batch(es) verified.")
    verify_batch.short_description = "Verify selected batch payments"
    list_display = [ 'amount', 'transaction_id', 'is_verified', 'verified_by']
    list_filter = ['is_verified']
    actions = ['verify_payments']

    def verify_payments(self, request, queryset):
        for payment in queryset:
            payment.is_verified = True
            payment.verified_by = request.user
            payment.verified_at = now()
            payment.save()

            # Update parent registration
            reg = payment.registration
            total_verified = reg.payments.filter(is_verified=True).aggregate(
                models.Sum('amount')
            )['amount__sum'] or 0

            total_due = reg.amount_paid
            if total_verified >= total_due:
                reg.payment_status = 'full'
                reg.registration_status = 'confirmed'
            elif total_verified > 0:
                reg.payment_status = 'partial'
            reg.save()

        self.message_user(request, f"{queryset.count()} payment(s) verified.")
    verify_payments.short_description = "Verify selected payments"

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('registration__registered_for', 'registration__yatra')