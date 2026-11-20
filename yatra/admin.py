from django.contrib import admin
from learning_material.models import Resource
from .models import *
from django.urls import reverse
from django.utils.html import format_html
from django.utils.numberformat import format as format_number
from django.urls import path
from decimal import Decimal
from django.db.models import Count, DecimalField, Exists, F, IntegerField, OuterRef, Prefetch, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce
import nested_admin
from .admin_forms import *

# Register your models here.


class YatraFormFieldInline(nested_admin.NestedTabularInline):
    model = YatraFormField
    extra = 0
    fields = ['name', 'label', 'field_type', 'options', 'is_required', 'order']
    form = YatraFormFieldForm


class YatraInstallmentInline(nested_admin.NestedTabularInline):
    model = YatraInstallment
    extra = 0
    fields = ['label', 'amount', 'order', 'start_date', 'end_date']
    verbose_name = "Legacy installment (no phase)"
    verbose_name_plural = "Legacy installments (no phase)"

    def get_queryset(self, request):
        return super().get_queryset(request).filter(phase__isnull=True)


class PhaseInstallmentInline(nested_admin.NestedTabularInline):
    model = YatraInstallment
    extra = 0
    fk_name = "phase"
    fields = ['label', 'amount', 'order', 'start_date', 'end_date']
    form = PhaseInstallmentForm


class RegistrationPhaseInline(nested_admin.NestedStackedInline):
    model = RegistrationPhase
    extra = 0
    fields = ['name']
    inlines = [PhaseInstallmentInline]


class YatraJourneyInline(nested_admin.NestedTabularInline):
    model = YatraJourney
    extra = 0
    form = YatraJourneyForm


class YatraAccommodationInline(nested_admin.NestedTabularInline):
    model = YatraAccommodation
    extra = 0
    form = YatraAccommodationForm


# -----------------------------
# Nested Custom Field Values
# -----------------------------
class YatraCustomFieldValueInline(nested_admin.NestedTabularInline):
    model = YatraCustomFieldValue
    extra = 0
    form = YatraCustomFieldValueForm



class YatraCustomFieldInline(nested_admin.NestedTabularInline):
    model = YatraCustomField
    extra = 0
    inlines = [YatraCustomFieldValueInline]   # <-- NESTED inside this inline

    
class YatraContactCategoryInline(nested_admin.NestedTabularInline):
    model = YatraContactCategory
    extra = 0
    form = YatraContactCategoryForm
    fields = ['title', 'numbers', 'order', 'show_in_rcs']


class YatraImportantNoteInline(nested_admin.NestedTabularInline):
    model = YatraImportantNote
    extra = 0
    form = YatraImportantNoteForm 
    fields = ['note', 'order', 'show_in_rcs']

class YatraResourceInline(nested_admin.NestedTabularInline):
    model = Resource
    extra = 0
    fields = ('title','subtitle','category','resource_type','language','link_url','thumbnail','order','is_active',)
    ordering = ('order',)


class RegistrationPolicyInline(nested_admin.NestedStackedInline):
    model = RegistrationPolicy
    extra = 0
    max_num = 1
    can_delete = False
    fields = ['requires_approval', 'min_chanting_rounds']
    verbose_name = "Registration Policy"
    verbose_name_plural = "Registration Policy"

    def _has_responses(self, yatra):
        cache_key = getattr(yatra, 'pk', None)
        response_cache = getattr(self, '_response_cache', {})
        if cache_key in response_cache:
            return response_cache[cache_key]

        from yatra_registration.models import YatraEligibility, YatraRegistration
        has_responses = (
            YatraEligibility.objects.filter(yatra=yatra).exists() or
            YatraRegistration.objects.filter(yatra=yatra).exists()
        )
        response_cache[cache_key] = has_responses
        self._response_cache = response_cache
        return has_responses

    def requires_approval_locked(self, obj):
        val = "Yes — mentor approval required for registration." if obj and obj.requires_approval else "No — Yatra is open to all"
        return format_html(
            '<strong>{}</strong><br>'
            '<small style="color:#b45309;">&#128274; Locked — approvals or registrations have already '
            'begin.</small>',
            val
        )
    requires_approval_locked.short_description = "Requires Approval"

    def get_readonly_fields(self, request, obj=None):
        if obj and self._has_responses(obj):
            return ['requires_approval_locked']
        return []

    def get_fields(self, request, obj=None):
        if obj and self._has_responses(obj):
            return ['requires_approval_locked', 'min_chanting_rounds']
        return ['requires_approval', 'min_chanting_rounds']


@admin.register(Yatra)
class YatraAdmin(nested_admin.NestedModelAdmin):
    class Media:
        css = {"all": ("yatra/css/custom_field_values.css",)}

    list_display = ('id', 'title', 'start_date', 'end_date', 'registered_capacity', 'total_collection', 'created_at')
    search_fields = ('title',)
    list_filter = ('title',)
    ordering = ('-created_at',)
    readonly_fields = ('poster_preview',)
    inlines = [RegistrationPolicyInline, YatraFormFieldInline, RegistrationPhaseInline,
               YatraInstallmentInline,
               YatraJourneyInline, YatraAccommodationInline, YatraCustomFieldInline,
               YatraContactCategoryInline, YatraImportantNoteInline,YatraResourceInline]

    def get_queryset(self, request):
        from payment.models import Payment
        from yatra_registration.models import YatraRegistration, YatraRegistrationInstallment

        started_installments = YatraRegistrationInstallment.objects.filter(
            Q(is_paid=True) | (Q(payment__isnull=False) & ~Q(payment__proof='')),
            registration_id=OuterRef('pk'),
        )
        started_registrations = (
            YatraRegistration.objects.filter(yatra_id=OuterRef('pk'))
            .exclude(status__in=['cancelled', 'refunded'])
            .filter(Q(status='substituted') | Q(is_complimentary=True) | Exists(started_installments))
            .order_by()
            .values('yatra_id')
            .annotate(total=Count('pk'))
            .values('total')
        )
        cancelled_registrations = (
            YatraRegistration.objects.filter(
                yatra_id=OuterRef('pk'), status__in=['cancelled', 'refunded'],
            )
            .filter(Q(is_complimentary=True) | Exists(started_installments))
            .order_by()
            .values('yatra_id')
            .annotate(total=Count('pk'))
            .values('total')
        )

        linked_installments = YatraRegistrationInstallment.objects.filter(
            payment_id=OuterRef('pk'),
            registration__yatra_id=OuterRef(OuterRef('pk')),
        )
        verified_totals = (
            Payment.objects.filter(status='verified')
            .filter(Exists(linked_installments))
            .order_by()
            .annotate(group_key=Value(1))
            .values('group_key')
            .annotate(total=Sum('total_amount'))
            .values('total')
        )
        cancelled_totals = (
            YatraRegistrationInstallment.objects.filter(
                registration__yatra_id=OuterRef('pk'),
                registration__status__in=['cancelled', 'refunded'],
                payment__status='verified',
            )
            .order_by()
            .values('registration__yatra_id')
            .annotate(total=Sum('installment__amount'))
            .values('total')
        )
        amount_field = DecimalField(max_digits=20, decimal_places=2)
        return (
            super().get_queryset(request)
            .annotate(started_registration_count=Coalesce(
                Subquery(started_registrations, output_field=IntegerField()),
                Value(0),
            ), cancelled_registration_count=Coalesce(
                Subquery(cancelled_registrations, output_field=IntegerField()),
                Value(0),
            ), verified_collection=Coalesce(
                Subquery(verified_totals, output_field=amount_field),
                Value(Decimal('0.00'), output_field=amount_field),
            ), cancelled_collection=Coalesce(
                Subquery(cancelled_totals, output_field=amount_field),
                Value(Decimal('0.00'), output_field=amount_field),
            ))
            .annotate(active_collection=F('verified_collection') - F('cancelled_collection'))
            .select_related('registration_policy')
            .prefetch_related(
                Prefetch(
                    'installments',
                    queryset=YatraInstallment.objects.filter(phase__isnull=True),
                    to_attr='_legacy_installments',
                )
            )
        )

    @admin.display(description='Registered / capacity', ordering='started_registration_count')
    def registered_capacity(self, obj):
        return f'{obj.started_registration_count} / {obj.capacity} ({obj.cancelled_registration_count} cancelled/refunded)'

    @admin.display(description='Total collection', ordering='active_collection')
    def total_collection(self, obj):
        def indian_amount(amount):
            return format_number(amount, '.', decimal_pos=2, grouping=(3, 2, 0),
                                 thousand_sep=',', force_grouping=True)

        return f"₹{indian_amount(obj.active_collection)} (₹{indian_amount(obj.cancelled_collection)} cancelled/refunded)"

    def get_inline_instances(self, request, obj=None):
        inline_instances = super().get_inline_instances(request, obj)

        # nested_admin may still render an empty inline heading even when
        # has_view_permission() returns False. Remove the legacy inline
        # instance itself unless this Yatra already has legacy installments.
        has_legacy_installments = bool(
            obj and getattr(obj, '_legacy_installments', None)
        )
        if not has_legacy_installments:
            inline_instances = [
                inline for inline in inline_instances
                if not isinstance(inline, YatraInstallmentInline)
            ]
        return inline_instances

    def poster_preview(self, obj):
        if obj.poster:
            return format_html('<img src="{}" style="max-height:200px; border-radius:8px;" />', obj.poster.url)
        return "No poster uploaded"
    poster_preview.short_description = "Poster Preview"


