from django.contrib import admin
from yatra.admin_views import yatra_bulk_offline_import
from .models import *
from django.urls import reverse
from django.utils.html import format_html
from django.urls import path
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
    list_display = ('id','title', 'location', 'start_date', 'end_date', 'capacity','payment_upi_id', 'created_at','bulk_import_link')
    search_fields = ('title', 'location')
    list_filter = ('start_date', 'location')
    ordering = ('-created_at',)
    inlines = [YatraFormFieldInline, YatraInstallmentInline]

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


