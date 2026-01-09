from django.contrib import admin
from .models import *

# Register your models here.
from django.contrib import admin
from .models import Event


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    # 🔹 List view
    list_display = (
        "title",
        "status",
        "start_datetime",
        "poster",
        "youtube_live_url",
        "is_active",
    )
    list_filter = (
        "event_type",
        "status",
        "is_active",
    )
    search_fields = ("title", "description")

    ordering = ("-start_datetime",)

    # 🔹 Read-only auto fields
    readonly_fields = ("created_at",)

    # 🔹 Admin field grouping (VERY IMPORTANT)
    fieldsets = (
        ("Basic Information", {
            "fields": (
                "title",
                "description",
                "poster",
            )
        }),

        ("Event Configuration", {
            "fields": (
                "event_type",
                "status",
                "is_active",
            )
        }),

        ("Schedule", {
            "fields": (
                "start_datetime",
                "end_datetime",
            )
        }),

        ("YouTube / Live Streaming", {
            "fields": (
                "youtube_live_url",
                "youtube_thumbnail",
                "youtube_replay_url",
            ),
            "classes": ("collapse",),
        }),

        ("Location Details", {
            "fields": (
                "location_name",
                "location_map_link",
            ),
            "classes": ("collapse",),
        }),

        ("Actions / Registration", {
            "fields": (
                "registration_link",
            ),
            "classes": ("collapse",),
        }),

        ("Metadata", {
            "fields": (
                "created_at",
            ),
        }),
    )

    # 🔹 Visual cues
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.order_by("-start_datetime")
