from django.contrib import admin
from .models import SubstitutionRequest
from yatra.admin_utils import ActiveYatraAdminMixin
from userProfile.admin_utils import format_profile_name

@admin.register(SubstitutionRequest)
class SubstitutionRequestAdmin(ActiveYatraAdminMixin, admin.ModelAdmin):
    admin_yatra_lookup = "registration__yatra"
    change_list_template = "admin/yatra_substitution/substitutionrequest_changelist.html"
    list_display = (
        "id",
        "registration",
        "initiator_display",
        "target_profile_display",
        "two_digit_code",
        "amount_paid",
        "created_at",
        "expires_at",
    )

    list_filter = (
        "created_at",
        "expires_at",
    )

    search_fields = (
        "registration__id",
        "initiator__first_name", "initiator__last_name", "initiator__initiated_name",
        "target_profile__first_name", "target_profile__last_name", "target_profile__initiated_name",
        "two_digit_code",
    )

    ordering = ("-created_at",)
    list_select_related = ("registration", "initiator", "target_profile")

    @admin.display(description="Initiator", ordering="initiator__first_name")
    def initiator_display(self, obj):
        return format_profile_name(obj.initiator)

    @admin.display(description="Target profile", ordering="target_profile__first_name")
    def target_profile_display(self, obj):
        return format_profile_name(obj.target_profile)
