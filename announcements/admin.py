from django.contrib import admin
from django.utils import timezone
from .models import Event


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):

    list_display = ("title", "category", "status", "start_datetime", "is_active")
    list_filter  = ("category", "status", "event_type", "is_active")
    search_fields = ("title", "description")
    ordering = ("-start_datetime",)
    readonly_fields = ("created_at",)

    # Fieldsets shown when ADDING a new entry (show everything so admin can decide)
    add_fieldsets = (
        ("Category", {
            "fields": ("category",),
            "description": "Pick the category first — it controls which fields matter.",
        }),
        ("Basic Information", {
            "fields": ("title", "description", "poster", "is_active"),
        }),
        ("Event Configuration", {
            "fields": ("event_type", "status"),
        }),
        ("Schedule", {
            "fields": ("start_datetime", "end_datetime"),
        }),
        ("YouTube / Live Streaming", {
            "fields": ("youtube_live_url", "youtube_thumbnail", "youtube_replay_url"),
            "classes": ("collapse",),
        }),
        ("Location", {
            "fields": ("location_name", "location_map_link"),
            "classes": ("collapse",),
        }),
        ("Registration", {
            "fields": ("registration_link",),
            "classes": ("collapse",),
        }),
        ("Metadata", {
            "fields": ("created_at",),
        }),
    )

    def get_fieldsets(self, request, obj=None):
        # New object — show all fields so admin can fill freely
        if obj is None:
            return self.add_fieldsets

        category = obj.category

        # ── Announcement & Notice: text only, no image/video/location ──────
        if category in ("announcement", "notice"):
            return (
                ("Category", {"fields": ("category",)}),
                ("Content", {
                    "fields": ("title", "description", "is_active"),
                    "description": "Keep description to a single line.",
                }),
                ("Schedule", {
                    "fields": ("start_datetime", "end_datetime"),
                }),
                ("Metadata", {"fields": ("created_at",)}),
            )

        # ── Workshop: image + details, no YouTube live ───────────────────
        if category == "workshop":
            return (
                ("Category", {"fields": ("category",)}),
                ("Basic Information", {
                    "fields": ("title", "description", "poster", "is_active"),
                }),
                ("Configuration", {
                    "fields": ("event_type", "status"),
                }),
                ("Schedule", {
                    "fields": ("start_datetime", "end_datetime"),
                }),
                ("Location", {
                    "fields": ("location_name", "location_map_link"),
                    "classes": ("collapse",),
                }),
                ("Registration / Link", {
                    "fields": ("registration_link",),
                    "classes": ("collapse",),
                }),
                ("Metadata", {"fields": ("created_at",)}),
            )

        # ── Event (default): all fields ──────────────────────────────────
        return (
            ("Category", {"fields": ("category",)}),
            ("Basic Information", {
                "fields": ("title", "description", "poster", "is_active"),
            }),
            ("Event Configuration", {
                "fields": ("event_type", "status"),
            }),
            ("Schedule", {
                "fields": ("start_datetime", "end_datetime"),
            }),
            ("YouTube / Live Streaming", {
                "fields": ("youtube_live_url", "youtube_thumbnail", "youtube_replay_url"),
                "classes": ("collapse",),
            }),
            ("Location", {
                "fields": ("location_name", "location_map_link"),
                "classes": ("collapse",),
            }),
            ("Registration", {
                "fields": ("registration_link",),
                "classes": ("collapse",),
            }),
            ("Metadata", {"fields": ("created_at",)}),
        )

