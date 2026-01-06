from django.contrib import admin
from userProfile.admin_utils import export_as_excel
from .models import *
from django.contrib import admin
from django.utils.timezone import localtime
from django.utils.html import format_html
from django.db.models import Prefetch, Max
from django.db.models import OuterRef, Subquery, BooleanField, DateTimeField


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = (
        'formatted_member_id',
        'profile_photo_preview',
        'user_username',
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
    actions = [export_as_excel]


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

    def user_username(self, obj):
        return obj.user.username if obj.user else "—"
    user_username.short_description = "User"
    user_username.admin_order_field = 'user__username'

    # ---------------------------
    # Mentor-related columns
    # ---------------------------

    def mentor_display(self, obj):
        return obj.mentor.formatted_member_id() if obj.mentor else "-"
    mentor_display.short_description = "Mentor ID"

    def mentor_request_approved(self, obj):
        if obj.last_request_is_approved is None:
            return "—"
        return "✅ Yes" if obj.last_request_is_approved else "❌ No"

    def mentor_request_approved_at(self, obj):
        if obj.last_request_approved_at:
            return localtime(obj.last_request_approved_at).strftime("%d %b %Y, %H:%M")
        return "—"

     # ---------------------------
    # Profile photo preview
    # ---------------------------

    def profile_photo_preview(self, obj):
        if obj.profile_picture:
            return format_html(
                '<img loading="lazy" src="{}" width="40" height="40" style="border-radius:50%; object-fit:cover;" />',
                obj.profile_picture.url
            )
        return "—"
    profile_photo_preview.short_description = "Photo"

    
    def has_add_permission(self, request):
        return False

    # Optional: also hide from change/view pages of related models
    def has_module_permission(self, request):
        return True  # Still show in admin menu
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)

        qs = qs.select_related('mentor','user')

        last_request_qs = MentorRequest.objects.filter(
            from_user=OuterRef('pk'),
            to_mentor=OuterRef('mentor_id'),
        ).order_by('-created_at')

        qs = qs.annotate(
            last_request_is_approved=Subquery(
                last_request_qs.values('is_approved')[:1],
                output_field=BooleanField(),
            ),
            last_request_approved_at=Subquery(
                last_request_qs.values('approved_at')[:1],
                output_field=DateTimeField(),
            ),
        )

        return qs

    
    


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



