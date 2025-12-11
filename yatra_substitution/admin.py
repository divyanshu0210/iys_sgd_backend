from django.contrib import admin
from .models import SubstitutionRequest

@admin.register(SubstitutionRequest)
class SubstitutionRequestAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "registration",
        "initiator",
        "target_profile",
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
        "initiator__full_name",
        "target_profile__full_name",
        "two_digit_code",
    )

    ordering = ("-created_at",)
