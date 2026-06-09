from django.contrib import admin
from learning_material.models import Resource
from yatra_registration.bulk_import_admin_views import yatra_bulk_offline_import
from .models import *
from django.urls import reverse
from django.utils.html import format_html
from django.urls import path
import nested_admin
from .admin_forms import *

# Register your models here.


class YatraFormFieldInline(nested_admin.NestedTabularInline):
    model = YatraFormField
    extra = 1
    fields = ['name', 'label', 'field_type', 'options', 'is_required', 'order']
    form = YatraFormFieldForm


class YatraInstallmentInline(nested_admin.NestedTabularInline):
    model = YatraInstallment
    extra = 1
    fields = ['label', 'amount', 'order']


class YatraJourneyInline(nested_admin.NestedTabularInline):
    model = YatraJourney
    extra = 1
    form = YatraJourneyForm


class YatraAccommodationInline(nested_admin.NestedTabularInline):
    model = YatraAccommodation
    extra = 1
    form = YatraAccommodationForm


# -----------------------------
# Nested Custom Field Values
# -----------------------------
class YatraCustomFieldValueInline(nested_admin.NestedTabularInline):
    model = YatraCustomFieldValue
    extra = 1
    form = YatraCustomFieldValueForm



class YatraCustomFieldInline(nested_admin.NestedTabularInline):
    model = YatraCustomField
    extra = 1
    inlines = [YatraCustomFieldValueInline]   # <-- NESTED inside this inline

    
class YatraContactCategoryInline(nested_admin.NestedTabularInline):
    model = YatraContactCategory
    extra = 1
    form = YatraContactCategoryForm
    fields = ['title', 'numbers', 'order', 'show_in_rcs']


class YatraImportantNoteInline(nested_admin.NestedTabularInline):
    model = YatraImportantNote
    extra = 1
    form = YatraImportantNoteForm 
    fields = ['note', 'order', 'show_in_rcs']

class YatraResourceInline(nested_admin.NestedTabularInline):
    model = Resource
    extra = 1
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
        from yatra_registration.models import YatraEligibility, YatraRegistration
        return (
            YatraEligibility.objects.filter(yatra=yatra).exists() or
            YatraRegistration.objects.filter(yatra=yatra).exists()
        )

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
    list_display = ('id','title', 'location', 'start_date', 'end_date', 'capacity','payment_upi_id', 'created_at')
    search_fields = ('title', 'location')
    list_filter = ('start_date', 'location')
    ordering = ('-created_at',)
    inlines = [RegistrationPolicyInline, YatraFormFieldInline, YatraInstallmentInline,
               YatraJourneyInline, YatraAccommodationInline, YatraCustomFieldInline,
               YatraContactCategoryInline, YatraImportantNoteInline,YatraResourceInline]


