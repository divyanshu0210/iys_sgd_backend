from django.contrib import admin
from yatra.admin_views import yatra_bulk_offline_import
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

    

@admin.register(Yatra)
class YatraAdmin(nested_admin.NestedModelAdmin):
    list_display = ('id','title', 'location', 'start_date', 'end_date', 'capacity','payment_upi_id', 'created_at','bulk_import_link')
    search_fields = ('title', 'location')
    list_filter = ('start_date', 'location')
    ordering = ('-created_at',)
    inlines = [YatraFormFieldInline, YatraInstallmentInline,YatraJourneyInline, YatraAccommodationInline, YatraCustomFieldInline]

    def bulk_import_link(self, obj):
        if not obj.is_registration_open:
            return "-"
        url = reverse('admin:yatra_bulk_offline_import', args=[obj.id])
        return format_html('<a href="{}" class="button">Bulk Registrations</a>', url)
    bulk_import_link.short_description = "Bulk Registeration"

    def get_urls(self):
        urls = super().get_urls()

        custom_urls = [
            path(
                'bulk-offline-import/<uuid:yatra_id>/',
                self.admin_site.admin_view(yatra_bulk_offline_import),
                name='yatra_bulk_offline_import',
            ),
        ]
        return custom_urls + urls


