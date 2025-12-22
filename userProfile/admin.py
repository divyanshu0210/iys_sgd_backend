from django.contrib import admin

from .models import *
from django.contrib import admin
from django.utils.timezone import localtime
from django.utils.html import format_html

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = (
        'formatted_member_id',
        'profile_photo_preview',
        'user',
        'user_type',
        'first_name',
        'last_name',
        'mobile',
        'center',
        'spiritual_master',
        'created_at',
        'mentor_display',
        'mentor_request_approved',
        'mentor_request_approved_at',
    )

    search_fields = (
        'member_id',
        'first_name',
        'last_name',
        'mobile',
        'aadhar_card_no',
        # 'country',
        'center',
        'spiritual_master',
    )

    list_filter = (
        'user_type',
        'gender',
        'marital_status',
        'country',
        'center',
        'is_initiated',
        'spiritual_master',
    )

    readonly_fields = ('member_id', 'created_at')
    ordering = ('-created_at',)

    def save_model(self, request, obj, form, change):
        """
        Auto-create MentorRequest when mentor is assigned in Admin
        """
        old_mentor = None
        if change:
            try:
                old = Profile.objects.get(pk=obj.pk)
                old_mentor = old.mentor
            except Profile.DoesNotExist:
                pass

        super().save_model(request, obj, form, change)

        # Only trigger if mentor was changed AND user is superuser
        if request.user.is_superuser and obj.mentor and (not change or old_mentor != obj.mentor):
            # Auto-create approved MentorRequest
            MentorRequest.objects.update_or_create(
                from_user=obj,
                to_mentor=obj.mentor,
                defaults={
                    'is_approved': True,
                    'message': 'Auto-approved by superuser assignment in admin',
                }
            )

    def formatted_member_id(self, obj):
        return f"{obj.member_id:06d}"
    formatted_member_id.short_description = "Member ID"

    
    # ---------------------------
    # Mentor-related columns
    # ---------------------------

    def mentor_display(self, obj):
        return obj.mentor.formatted_member_id() if obj.mentor else "-"
    mentor_display.short_description = "Mentor ID"

    def mentor_request_approved(self, obj):
        req = MentorRequest.objects.filter(
            from_user=obj,
            to_mentor=obj.mentor
        ).order_by('-created_at').first()

        if not req:
            return "—"

        return "✅ Yes" if req.is_approved else "❌ No"
    mentor_request_approved.short_description = "Mentor Approved"

    def mentor_request_approved_at(self, obj):
        req = MentorRequest.objects.filter(
            from_user=obj,
            to_mentor=obj.mentor,
            is_approved=True
        ).order_by('-approved_at').first()

        if req and req.approved_at:
            return localtime(req.approved_at).strftime("%d %b %Y, %H:%M")
        return "—"
    mentor_request_approved_at.short_description = "Approved At"

     # ---------------------------
    # Profile photo preview
    # ---------------------------

    def profile_photo_preview(self, obj):
        if obj.profile_picture:
            return format_html(
                '<img src="{}" width="40" height="40" style="border-radius:50%; object-fit:cover;" />',
                obj.profile_picture.url
            )
        return "—"
    profile_photo_preview.short_description = "Photo"



    
    def has_add_permission(self, request):
        return False

    # Optional: also hide from change/view pages of related models
    def has_module_permission(self, request):
        return True  # Still show in admin menu


class MentorOnlyFilter(admin.SimpleListFilter):
    title = "Mentor"
    parameter_name = "to_mentor"

    def lookups(self, request, model_admin):
        # Only mentors appear in filter list
        mentors = Profile.objects.filter(user_type="mentor")
        return [
            (mentor.id, f"({mentor.formatted_member_id()}) {mentor}")
            for mentor in mentors
        ]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(to_mentor_id=self.value())
        return queryset


@admin.register(MentorRequest)
class MentorRequestAdmin(admin.ModelAdmin):
    list_display = ('id','from_user', 'to_mentor', 'is_approved','approved_at','created_at')
    search_fields = (
        'from_user__first_name',
        'to_mentor__first_name',
        'from_user__member_id',
        'to_mentor__member_id',
    )
    list_filter = ('is_approved', 'created_at','approved_at',MentorOnlyFilter)
    ordering = ('-created_at',)

    
    def has_add_permission(self, request):
        return False

    # Optional: also hide from change/view pages of related models
    def has_module_permission(self, request):
        return True  # Still show in admin menu



