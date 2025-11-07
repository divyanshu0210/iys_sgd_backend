from django.contrib import admin

from .models import *


@admin.register(Yatra)
class YatraAdmin(admin.ModelAdmin):
    list_display = ('title', 'location', 'start_date', 'end_date', 'capacity', 'created_at')
    search_fields = ('title', 'location')
    list_filter = ('start_date', 'location')
    ordering = ('-created_at',)


from django.contrib import admin
from .models import Profile


from django.contrib import admin
from .models import Profile

@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = (
        'formatted_member_id',
        'user',
        'user_type',
        'first_name',
        'last_name',
        'mobile',
        'aadhar_card_no',
        'country',
        'center',
        'is_initiated',
        'spiritual_master',
        'no_of_chanting_rounds',  # ✅ Display in admin list
        'created_at',
    )

    search_fields = (
        'member_id',
        'first_name',
        'last_name',
        'mobile',
        'aadhar_card_no',
        'country',
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

    def formatted_member_id(self, obj):
        return f"{obj.member_id:06d}"
    formatted_member_id.short_description = "Member ID"




@admin.register(YatraRegistration)
class YatraRegistrationAdmin(admin.ModelAdmin):
    list_display = ('yatra', 'registered_for', 'registrant', 'status', 'registered_at')
    search_fields = ('yatra__title', 'registered_for__full_name', 'registrant__full_name')
    list_filter = ('status', 'yatra')
    ordering = ('-registered_at',)


# ✅ NEW: Mentor Request Admin
@admin.register(MentorRequest)
class MentorRequestAdmin(admin.ModelAdmin):
    list_display = ('id','from_user', 'to_mentor', 'is_approved', 'created_at')
    search_fields = (
        'from_user__first_name',
        'to_mentor__first_name',
        'from_user__member_id',
        'to_mentor__member_id',
    )
    list_filter = ('is_approved', 'created_at')
    ordering = ('-created_at',)