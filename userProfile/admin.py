from django.contrib import admin
from userProfile.admin_utils import export_as_excel, format_profile_name
from .models import *
from django.contrib import admin
from django.utils.timezone import localtime
from django.utils.html import format_html, format_html_join
from django.db.models import Prefetch, Max, Q
from django.db.models import OuterRef, Subquery, BooleanField, DateTimeField
from django import forms
from html import unescape
from uuid import UUID
from django.utils.html import strip_tags


class BaceAdminForm(forms.ModelForm):
    class Meta:
        model = Bace
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['counsellor'].required = True
        self.fields['counsellor'].queryset = Profile.objects.filter(user_type='counsellor').order_by('first_name', 'last_name')
        self.fields['mentors'].queryset = Profile.objects.filter(
            Q(user_type__in=['mentor', 'counsellor']) | Q(user__is_superuser=True)
        ).order_by('first_name', 'last_name')
        # The dual-list selector uses ModelChoiceField labels, not list_display.
        self.fields['mentors'].label_from_instance = lambda mentor: unescape(
            strip_tags(format_profile_name(mentor, inline=True))
        )

    def clean(self):
        cleaned_data = super().clean()
        counsellor = cleaned_data.get('counsellor')
        mentors = cleaned_data.get('mentors')

        if counsellor and mentors is not None and mentors.filter(pk=counsellor.pk).exists():
            self.add_error(
                'mentors',
                'The counsellor cannot also be assigned as a mentor for the same Bace.',
            )

        return cleaned_data


class OtherCenterInline(admin.TabularInline):
    model = OtherCenter
    extra = 1
    fields = ('name', 'is_active')


@admin.register(Bace)
class BaceAdmin(admin.ModelAdmin):
    form = BaceAdminForm
    list_display = ('name', 'is_active', 'counsellor_display', 'mentors_display')
    list_select_related = ('counsellor',)
    list_filter = ('is_active',)
    search_fields = ('name', 'counsellor__first_name', 'counsellor__last_name')
    filter_horizontal = ('mentors',)
    inlines = [OtherCenterInline]

    @admin.display(description='Counsellor', ordering='counsellor__first_name')
    def counsellor_display(self, obj):
        return format_profile_name(obj.counsellor)

    def get_inline_instances(self, request, obj=None):
        inline_instances = super().get_inline_instances(request, obj)
        if not obj or obj.name.strip().lower() != "others":
            return []
        return inline_instances

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related(
            Prefetch('mentors', queryset=Profile.objects.order_by('first_name', 'last_name', 'pk'))
        )

    @admin.display(description='Mentors')
    def mentors_display(self, obj):
        mentors = list(obj.mentors.all())
        if not mentors:
            return '—'
        return format_html_join(', ', '{}', ((format_profile_name(mentor, inline=True),) for mentor in mentors))


class ProfileMentorFilter(admin.SimpleListFilter):
    title = 'Mentor'
    parameter_name = 'assigned_mentor'

    def lookups(self, request, model_admin):
        assigned_ids = Profile.objects.exclude(mentor__isnull=True).values('mentor_id')
        mentors = Profile.objects.filter(pk__in=assigned_ids).order_by('first_name', 'last_name', 'pk')
        return [
            (str(mentor.pk), unescape(strip_tags(format_profile_name(mentor, inline=True))))
            for mentor in mentors
        ] + [('unassigned', 'No mentor')]

    def queryset(self, request, queryset):
        if not self.value():
            return queryset
        if self.value() == 'unassigned':
            return queryset.filter(mentor__isnull=True)
        try:
            return queryset.filter(mentor_id=UUID(self.value()))
        except (ValueError, TypeError, AttributeError):
            return queryset.none()


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = (
        'formatted_member_id',
        'profile_photo_preview',
        'user_username',
        'user_type',
        'display_name',
        'dob',
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
        'user__username',
        'first_name',
        'last_name',
        'initiated_name',
        'mobile',
        'aadhar_card_no',
        # 'country',
        'center',
        'spiritual_master',
    )

    list_filter = (
        ProfileMentorFilter,
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
        return f"{obj.member_id:06d}" if obj.member_id is not None else "-"
    formatted_member_id.short_description = "Member ID"

    @admin.display(description="Full name", empty_value="—")
    def display_name(self, obj):
        return format_profile_name(obj)

    def user_username(self, obj):
        return obj.user.username if obj.user else "—"
    user_username.short_description = "User"
    user_username.admin_order_field = 'user__username'

    # ---------------------------
    # Mentor-related columns
    # ---------------------------

    def mentor_display(self, obj):
        return format_profile_name(obj.mentor)
    mentor_display.short_description = "Mentor Name"

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
    list_display = (
        'id',
        'from_user_display',
        'requested_bace_display',
        'to_mentor_display',
        'is_approved',
        'approved_at',
        'created_at',
    )
    readonly_fields = ('requested_bace_display',)
    # exclude = ('requested_bace',)
    search_fields = (
        'from_user__first_name',
        'from_user__last_name',
        'from_user__initiated_name',
        'to_mentor__first_name',
        'to_mentor__last_name',
        'to_mentor__initiated_name',
        'from_user__member_id',
        'to_mentor__member_id',
        'from_user__center',
        'requested_bace__name',
    )
    list_filter = ('is_approved', 'requested_bace', 'created_at', 'approved_at', MentorOnlyFilter)
    ordering = ('-created_at',)

    @admin.display(description='From user', ordering='from_user__first_name')
    def from_user_display(self, obj):
        return format_profile_name(obj.from_user)

    @admin.display(description='To mentor', ordering='to_mentor__first_name')
    def to_mentor_display(self, obj):
        return format_profile_name(obj.to_mentor)

    def get_queryset(self, request):
        queryset = super().get_queryset(request).select_related(
            'from_user', 'to_mentor', 'requested_bace'
        )
        self._configured_bace_names = {
            name.casefold(): name
            for name in Bace.objects.values_list('name', flat=True)
            if name
        }
        return queryset

    @admin.display(description='Requested Bace', ordering='requested_bace__name')
    def requested_bace_display(self, obj):
        routing_bace = obj.requested_bace.name if obj.requested_bace else None
        selected_center = obj.from_user.center if obj.from_user else None

        if selected_center and selected_center != 'Others':
            configured_bace = self._configured_bace_names.get(selected_center.casefold())
            if configured_bace:
                return configured_bace
            return f'Others ({selected_center})'
        return routing_bace or selected_center or '-'

    
    def has_add_permission(self, request):
        return False

    # Optional: also hide from change/view pages of related models
    def has_module_permission(self, request):
        return True  # Still show in admin menu



