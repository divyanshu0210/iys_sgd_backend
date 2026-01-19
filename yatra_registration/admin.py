from django.contrib import admin
from django.contrib.admin import RelatedOnlyFieldListFilter
from userProfile.admin_utils import export_as_excel
from yatra_registration.bulk_import_admin_views import yatra_bulk_offline_import
from .models import *
from django.urls import path
from .admin_views import *
from django.utils import timezone
from django import forms
from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from django.db.models import Prefetch
from django.contrib.admin import SimpleListFilter

class YatraListFilter(SimpleListFilter):
    title = 'Yatra'
    parameter_name = 'yatra'

    def lookups(self, request, model_admin):
        # show all yatras in the filter, even if no registrations exist
        from yatra.models import Yatra
        return [(y.id, y.title) for y in Yatra.objects.all()]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(yatra_id=self.value())
        return queryset
    

class RCSDownloadedFilter(SimpleListFilter):
    title = "RCS Downloaded"
    parameter_name = "rcs_downloaded"

    def lookups(self, request, model_admin):
        return (
            ("yes", "Yes"),
            ("no", "No"),
        )

    def queryset(self, request, queryset):
        value = self.value()

        if value == "yes":
            return queryset.filter(
                rcs_download_event__count__gt=0
            )

        if value == "no":
            return queryset.filter(
                rcs_download_event__isnull=True
            ) | queryset.filter(
                rcs_download_event__count=0
            )

        return queryset

# ──────────────────────────────────────────────────────────────
# FIXED & WORKING: Dynamic Custom Field Dropdown in Inline
# ──────────────────────────────────────────────────────────────

from django import forms
class RegistrationCustomFieldValueForm(forms.ModelForm):
    class Meta:
        model = RegistrationCustomFieldValue
        fields = ['custom_field', 'custom_field_value']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Safely get the custom field
        custom_field = None
        if self.instance and self.instance.pk and self.instance.custom_field:
            custom_field = self.instance.custom_field
        elif self.initial.get('custom_field'):
            try:
                custom_field = YatraCustomField.objects.get(id=self.initial['custom_field'])
            except (YatraCustomField.DoesNotExist, ValueError):
                pass

        if custom_field:
            self.fields['custom_field_value'].queryset = custom_field.values.all()
        else:
            self.fields['custom_field_value'].queryset = YatraCustomFieldValue.objects.none()


class RegistrationCustomFieldValueInline(admin.TabularInline):
    model = RegistrationCustomFieldValue
    form = RegistrationCustomFieldValueForm
    extra = 0
    fields = ['custom_field', 'custom_field_value']
    can_delete = True

    def get_formset(self, request, obj=None, **kwargs):
        if obj is None:
            return super().get_formset(request, obj, **kwargs)

        # Get all custom fields for this yatra
        yatra_fields = list(obj.yatra.custom_fields.all())
        existing_field_ids = set(
            obj.custom_values.values_list('custom_field_value__custom_field_id', flat=True)
        )
        missing_fields = [f for f in yatra_fields if f.id not in existing_field_ids]

        # We'll add missing fields as extra forms
        base_formset = super().get_formset(request, obj, **kwargs)

        class CustomFormset(base_formset):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.extra = len(missing_fields)  # Dynamic extra

                # Only touch the extra blank forms
                extra_forms = self.forms[-len(missing_fields):] if missing_fields else []
                for i, form in enumerate(extra_forms):
                    if i >= len(missing_fields):
                        break
                    field = missing_fields[i]
                    form.fields['custom_field'].initial = field.id
                    form.fields['custom_field'].queryset = YatraCustomField.objects.filter(id=field.id)
                    form.fields['custom_field_value'].queryset = field.values.all()

        return CustomFormset
    

@admin.display(description="Custom Field")
def custom_field_name(self, instance):
    if instance.custom_field_value:
        return f"{instance.custom_field_value.custom_field.field_name}: {instance.custom_field_value.value}"
    return "-"

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


class RegistrationAccommodationInline(admin.TabularInline):
    model = RegistrationAccommodation
    extra = 0

class RegistrationJourneyInline(admin.TabularInline):
    model = RegistrationJourney
    extra = 0

# class RegistrationCustomFieldValueInline(admin.TabularInline):
    # model = RegistrationCustomFieldValue
    # extra = 0

@admin.register(YatraRegistration)
class YatraRegistrationAdmin(admin.ModelAdmin):
    list_display = (
        'registered_for',
        'yatra',
        'registered_by',
        'mentor_full_name',
        'registration_status',
        'total_amount_display',
        'paid_amount_display',
        'installments_status',
        'registered_at',
        'accommodation_summary',
        'journey_summary',
        'custom_field_summary',
        'rcs_downloads'
    )
    search_fields = (
        'yatra__title',
        'registered_for__first_name',
        'registered_for__last_name',
        'registered_by__first_name',
        'registered_by__last_name',
    )
    list_filter = (
        YatraListFilter,'status', 'registered_at',RCSDownloadedFilter,)
    ordering = ('-registered_at',)
    # list_per_page = 25            
    # show_full_result_count = False

    readonly_fields = ('total_amount_display', 'paid_amount_display', 'installments_status')

    inlines = [
        RegistrationAccommodationInline,
        RegistrationJourneyInline,
        RegistrationCustomFieldValueInline
    ]
    actions = [export_as_excel]

    @admin.display(description="Status", ordering='status')
    def registration_status(self, obj):
        status_map = {
            'pending': {
                'text': 'NOT STARTED',
                'bg': '#e2e3e5',      # light gray
                'color': '#383d41',   # dark gray
                'icon': '○'
            },
            'partial': {
                'text': 'INCOMPLETE',
                'bg': '#fff3cd',      # light yellow
                'color': '#856404',   # amber/brown
                'icon': '●'
            },
            'paid': {
                'text': 'CONFIRMED',
                'bg': '#d4edda',      # light green
                'color': '#155724',   # dark green
                'icon': '✓'
            },
            'substituted': {
                'text': 'SUBSTITUTED',
                'bg': '#cce5ff',      # light blue
                'color': '#004085',   # dark blue
                'icon': '⇄'           # double arrow (substitution symbol)
            },
            'refunded': {
                'text': 'REFUNDED',
                'bg': '#f8d7da',      # light red
                'color': '#721c24',   # dark red
                'icon': '↩'           # left arrow (refund symbol)
            },
            'cancelled': {
                'text': 'CANCELLED',
                'bg': '#f8d7da',      # same light red as refunded (both negative)
                'color': '#721c24',
                'icon': '✗'
            },
            'attended': {
                'text': 'ATTENDED',
                'bg': '#d1ecf1',      # light cyan
                'color': '#0c5460',   # dark teal
                'icon': '✓✓'          # double check (completed/attended)
            },
        }
        config = status_map.get(obj.status, status_map['pending'])
        
        return format_html(
            '<span style="background:{}; color:{}; padding:5px 12px; border-radius:20px; '
            'font-weight:700; font-size:11px; white-space:nowrap; display:inline-block; '
            'border:1px solid {}40; box-shadow:0 1px 2px rgba(0,0,0,0.1);">'
            '{} {}</span>',
            config['bg'], config['color'], config['color'],
            config['icon'], config['text']
        )

# ──────────────────────────────────────────────────────────────
# for bulk edit view
    change_list_template = "admin/yatra_registration/bulk_edit_changelist.html"
    
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                'bulk-edit/<uuid:yatra_id>/',
                self.admin_site.admin_view(bulk_edit_view),
                name='yatra_registration_bulk_edit',
            ),
             path(
                'bulk-offline-import/<uuid:yatra_id>/',
                self.admin_site.admin_view(yatra_bulk_offline_import),
                name='yatra_bulk_offline_import',
            ),
        ]
        return custom_urls + urls
    
    def changelist_view(self, request, extra_context=None):
        # Get the current filtered Yatra (if any)
        yatra_id = request.GET.get('yatra__id__exact') or request.GET.get('yatra')
        yatra = None
        if yatra_id:
            try:
                yatra = Yatra.objects.get(id=yatra_id)
            except (Yatra.DoesNotExist, ValueError):
                pass

        # Pass it to the template
        extra_context = extra_context or {}
        extra_context['yatra'] = yatra

        return super().changelist_view(request, extra_context=extra_context)
#──────────────────────────────────────────────────────────────
#other amount and installment methods
    # Clean display methods (no colors, no HTML)
    def total_amount_display(self, obj):
        return f"₹{sum(i.amount for i in getattr(obj.yatra, '_pref_yatra_installments', []))}"  
    
    total_amount_display.short_description = "Total Amount"
    total_amount_display.admin_order_field = 'total_amount'

    def paid_amount_display(self, obj):
        return f"₹{sum(i.installment.amount for i in getattr(obj, '_pref_installments', []) if i.is_paid)}"
    paid_amount_display.short_description = "Paid"
    paid_amount_display.admin_order_field = 'paid_amount'

    @admin.display(description="Installment Status")
    def installments_status(self, obj):
        def compute():
            yatra_installments = getattr(obj.yatra, '_pref_yatra_installments', [])
            reg_installments = {ri.installment_id: ri for ri in getattr(obj, '_pref_installments', [])}

            items = []
            for inst in yatra_installments:
                ri = reg_installments.get(inst.id)

                if ri:
                    if ri.is_paid:
                        status = "Paid"
                    elif ri.payment:
                        status = "Verification Pending"
                    else:
                        status = "Due"
                else:
                    status = "Due"

                items.append(f"{inst.label} ({status})")

            return format_html("<br>".join(items)) if items else "No installments defined"

        return self._cache(obj, 'installments', compute)

    @admin.display(description="Accommodation")
    def accommodation_summary(self, obj):
        def compute():
            allocations = getattr(obj, '_pref_accommodations', [])
            if not allocations:
                return "No accommodation assigned"

            html = ["<table style='width:100%; border-collapse:collapse; font-family:system-ui;'>"]
            html.append("""
                <tr style='background:#f7f7f7; font-weight:600;'>
                    <td style='padding:8px;'>Place</td>
                    <td style='padding:8px;width:35%;'>Room/Bed</td>
                </tr>
            """)

            for idx, a in enumerate(allocations):
                bg = "#ffffff" if idx % 2 == 0 else "#f9f9f9"
                html.append(f"""
                    <tr style="background:{bg}; border-bottom:1px solid #eee;">
                        <td style="padding:8px; font-weight:600;">{a.accommodation.place_name}</td>
                        <td style="padding:8px;">
                            Room: <strong>{a.room_number or '—'}</strong><br>
                            Bed: <strong>{a.bed_number or '—'}</strong>
                        </td>
                    </tr>
                """)

            html.append("</table>")
            return format_html("".join(html))

        return self._cache(obj, 'accommodation', compute)

    @admin.display(description="Journey")
    def journey_summary(self, obj):
        def compute():
            journeys = getattr(obj, '_pref_journeys', [])
            if not journeys:
                return "No journey assigned"

            html = ["<table style='width:100%; border-collapse:collapse; font-family:system-ui;'>"]
            html.append("""
                <tr style='background:#f7f7f7; font-weight:600;'>
                    <td style='padding:8px;width:25%;'>Type</td>
                    <td style='padding:8px;width:45%;'>Route</td>
                    <td style='padding:8px;'>Vehicle/Seat</td>
                </tr>
            """)

            for idx, j in enumerate(journeys):
                bg = "#ffffff" if idx % 2 == 0 else "#f9f9f9"
                html.append(f"""
                    <tr style="background:{bg}; border-bottom:1px solid #eee;">
                        <td style="padding:8px; font-weight:600;">{j.journey.type.upper()}</td>
                        <td style="padding:8px;">{j.journey.from_location} → {j.journey.to_location}</td>
                        <td style="padding:8px;">
                            Vehicle: <strong>{j.vehicle_number or '—'}</strong><br>
                            Seat: <strong>{j.seat_number or '—'}</strong>
                        </td>
                    </tr>
                """)

            html.append("</table>")
            return format_html("".join(html))

        return self._cache(obj, 'journey', compute)
    
        
    @admin.display(description="Custom Fields")
    def custom_field_summary(self, obj):
        values = getattr(obj, '_pref_custom_values', [])

        if not values:
            return "No additional info"

        html = ["<table style='width:100%; border-collapse:collapse; font-family:system-ui;'>"]

        for v in values:
            field = v.custom_field_value.custom_field.field_name
            value = v.custom_field_value.value

            html.append(f"""
                <tr style="border-bottom:1px solid #eee;">
                    <td style="padding:8px; font-weight:600; width:40%;">{field}</td>
                    <td style="padding:8px;">{value}</td>
                </tr>
            """)

        html.append("</table>")
        return format_html("".join(html))


    @admin.display(description="RCS Downloads")
    def rcs_downloads(self, obj):
        event = getattr(obj, "_pref_rcs_downloads", None)

        if not event or event.count == 0:
            return "0"

        times = [
            timezone.localtime(
                timezone.datetime.fromisoformat(ts)
            ).strftime("%d %b %Y %H:%M")
            for ts in reversed(event.timestamps)
        ]
        tooltip_html= "HISTORY\n──────────\n" + "\n".join(times)
        last = timezone.localtime(event.last_downloaded_at).strftime(
            "%d %b %Y %H:%M"
        )

        return format_html(
            """
            <span title="{}"
                style="
                    cursor: pointer;
                    border-bottom: 1px dotted #666;
                    white-space: nowrap;
                ">
                {} (last: {})
            </span>
            """,
            tooltip_html,
            event.count,
            last
        )
#──────────────────────────────────────────────────────────────
    def mentor_full_name(self, obj):
        """Return mentor full name of the person who is registered_for."""
        if obj.registered_for and obj.registered_for.mentor:
            first = obj.registered_for.mentor.first_name or ""
            last = obj.registered_for.mentor.last_name or ""
            return f"{first} {last}".strip()
        return "-"
    mentor_full_name.short_description = "Mentor Name"

# ──────────────────────────────────────────────────────────────
    def has_add_permission(self, request):
        return False

    # Optional: also hide from change/view pages of related models
    def has_module_permission(self, request):
        return True  # Still show in admin menu

    def get_queryset(self, request):
        qs = super().get_queryset(request)

        return qs.select_related(
            'yatra',
            'registered_for',
            'registered_for__mentor',
            'registered_by',
        ).prefetch_related(
               Prefetch(
            'rcs_download_event',
            queryset=RCSDownloadEvent.objects.order_by('created_at'),
            to_attr='_pref_rcs_downloads',
            ),
            
            Prefetch(
                'installments',
                queryset=YatraRegistrationInstallment.objects.select_related('installment'),
                to_attr='_pref_installments',
            ),
            Prefetch(
                'yatra__installments',
                to_attr='_pref_yatra_installments',
            ),
               Prefetch(
            'accommodation_allocations',
            queryset=RegistrationAccommodation.objects.select_related('accommodation'),
            to_attr='_pref_accommodations',
            ),
            Prefetch(
                'journey_allocations',
                queryset=RegistrationJourney.objects.select_related('journey'),
                to_attr='_pref_journeys',
            ),
            Prefetch(
                'custom_values',
                queryset=RegistrationCustomFieldValue.objects.select_related(
                    'custom_field_value__custom_field'
                ),
                to_attr='_pref_custom_values',
            ),
        )
    
    def _cache(self, obj, key, compute_fn):
        if not hasattr(obj, '_admin_cache'):
            obj._admin_cache = {}
        if key not in obj._admin_cache:
            obj._admin_cache[key] = compute_fn()
        return obj._admin_cache[key]




