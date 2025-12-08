from django.contrib import admin
from .models import *
from django.urls import path
from .admin_views import *

# admin.py (inside your YatraRegistrationAdmin file)

from django import forms
from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html


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
    )
    search_fields = (
        'yatra__title',
        'registered_for__full_name',
        'registered_for__first_name',
        'registered_for__last_name',
        'registered_by__full_name',
    )
    list_filter = ('yatra','status', 'registered_at')
    ordering = ('-registered_at',)
    readonly_fields = ('total_amount_display', 'paid_amount_display', 'installments_status')
    inlines = [
        RegistrationAccommodationInline,
        RegistrationJourneyInline,
        RegistrationCustomFieldValueInline
    ]

    @admin.display(description="Status", ordering='status')
    def registration_status(self, obj):
        status_map = {
            'paid': {
                'text': 'CONFIRMED',
                'bg': '#d4edda',
                'color': '#155724',
                'icon': '✓'
            },
            'partial': {
                'text': 'INCOMPLETE',
                'bg': '#fff3cd',
                'color': '#856404',
                'icon': '●'
            },
            'pending': {
                'text': 'NOT STARTED',
                'bg': '#e2e3e5',
                'color': '#383d41',
                'icon': '○'
            },
            'cancelled': {
                'text': 'CANCELLED',
                'bg': '#f8d7da',
                'color': '#721c24',
                'icon': '✗'
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

    @admin.display(description="Accommodation")
    def accommodation_summary(self, obj):
        allocations = obj.accommodation_allocations.all()
        if not allocations:
            return "No accommodation assigned"

        html = "<table style='width:100%; border-collapse:collapse; font-family:system-ui;'>"
        html += """
            <tr style='background:#f7f7f7; font-weight:600;'>
                <td style='padding:8px; '>Place</td>
                <td style='padding:8px;width:35%;'>Room/Bed</td>
            </tr>
        """

        for idx, a in enumerate(allocations):
            bg = "#ffffff" if idx % 2 == 0 else "#f9f9f9"
            place = a.accommodation.place_name
            room = a.room_number or "—"
            bed = a.bed_number or "—"

            html += f"""
            <tr style="background:{bg}; border-bottom:1px solid #eee;">
                <td style="padding:8px; font-weight:600;">{place}</td>
                <td style="padding:8px;">
                    Room: <strong>{room}</strong> <br> Bed: <strong>{bed}</strong>
                </td>
            </tr>
            """

        html += "</table>"
        return format_html(html)


    @admin.display(description="Journey")
    def journey_summary(self, obj):
        journeys = obj.journey_allocations.all()
        if not journeys:
            return "No journey assigned"

        html = "<table style='width:100%; border-collapse:collapse; font-family:system-ui;'>"
        html += """
            <tr style='background:#f7f7f7; font-weight:600;'>
                <td style='padding:8px; width:25%;'>Type</td>
                <td style='padding:8px; width:45%;'>Route</td>
                <td style='padding:8px;'>Vehicle/Seat</td>
            </tr>
        """

        for idx, j in enumerate(journeys):
            bg = "#ffffff" if idx % 2 == 0 else "#f9f9f9"
            type_ = j.journey.type.upper()
            route = f"{j.journey.from_location} → {j.journey.to_location}"
            vehicle = j.vehicle_number or "—"
            seat = j.seat_number or "—"

            html += f"""
            <tr style="background:{bg}; border-bottom:1px solid #eee;">
                <td style="padding:8px; font-weight:600;">{type_}</td>
                <td style="padding:8px;">{route}</td>
                <td style="padding:8px;">
                    Vehicle: <strong>{vehicle}</strong> <br/> Seat: <strong>{seat}</strong>
                </td>
            </tr>
            """

        html += "</table>"
        return format_html(html)


    @admin.display(description="Custom Fields")
    def custom_field_summary(self, obj):
        values = obj.custom_values.all()
        if not values:
            return "No additional info"
        
        html = "<table style='width:100%; border-collapse:collapse; font-family:system-ui;'>"
        for v in values:
            field = v.custom_field_value.custom_field.field_name
            value = v.custom_field_value.value
            html += f"""
            <tr style="border-bottom:1px solid #eee;">
                <td style="padding:8px; font-weight:600; width:40%;">{field}</td>
                <td style="padding:8px;">{value}</td>
            </tr>
            """
        html += "</table>"
        return format_html(html)
    # custom_field_summary.short_description = "Custom Fields"
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
        return f"₹{obj.total_amount}"
    
    total_amount_display.short_description = "Total Amount"
    total_amount_display.admin_order_field = 'total_amount'

    def paid_amount_display(self, obj):
        return f"₹{obj.paid_amount}"
    
    paid_amount_display.short_description = "Paid"
    paid_amount_display.admin_order_field = 'paid_amount'

    def installments_status(self, obj):
        items = []

        all_yatra_installments = obj.yatra.installments.all().order_by('order')

        for inst in all_yatra_installments:
            reg_inst = obj.installments.filter(installment=inst).first()

            if reg_inst:
                if reg_inst.is_paid:
                    status = "Paid"
                elif reg_inst.payment and not reg_inst.is_paid:
                    status = "Verification Pending"
                else:
                    status = "Due"
            else:
                status = "Due"

            items.append(f"{inst.label} ({status})")

        if not items:
            return "No installments defined"

        # 🔥 use <br> for line breaks, format_html to mark safe
        return format_html("<br>".join(items))

    installments_status.short_description = "Installment Status"


    # def installments_status(self, obj):
    #     """
    #     Show status of all installments for this registration:
    #     - Paid → "Paid"
    #     - Verification Pending → "Verification Pending"
    #     - Due → "Due"
    #     """
    #     items = []

    #     # Get all installments defined in Yatra
    #     all_yatra_installments = obj.yatra.installments.all().order_by('order')

    #     for inst in all_yatra_installments:
    #         # Try to get registration installment
    #         reg_inst = obj.installments.filter(installment=inst).first()

    #         if reg_inst:
    #             if reg_inst.is_paid:
    #                 status = "Paid"
    #             elif reg_inst.payment and not reg_inst.is_paid:
    #                 status = "Verification Pending"
    #             else:
    #                 status = "Due"
    #         else:
    #             status = "Due"  # Installment not yet created

    #         items.append(f"{inst.label} ({status})")

    #     return " \n ".join(items) if items else "No installments defined"

    # installments_status.short_description = "Installment Status"
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


# @admin.register(YatraRegistrationInstallment)
# class YatraRegistrationInstallmentAdmin(admin.ModelAdmin):
    
#     list_display = (
#         'registration', 
#         'installment', 
#         'payment',
#         'is_paid', 
#         'paid_at', 
#         'verified_by',
#         'verified_at'
#     )
#     list_filter = ('is_paid', 'paid_at', 'verified_at')
#     search_fields = (
#         'registration__registered_for__first_name',
#         'registration__registered_for__last_name',
#         'payment__transaction_id'
#     )
#     readonly_fields = ('paid_at',)

#     def uploaded_at(self, obj):
#         return obj.payment.uploaded_at if obj.payment else None
#     uploaded_at.short_description = "Uploaded At"

