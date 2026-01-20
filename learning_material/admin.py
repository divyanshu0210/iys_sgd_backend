from django.contrib import admin

from learning_material.models import *

# Register your models here.
@admin.register(Resource)
class ResourceAdmin(admin.ModelAdmin):
    list_display = (
        'title',
        'category',
        'resource_type',
        'language',
        'yatra',
        'event',
        'is_active',
        'order',
    )

    list_filter = (
        'category',
        'resource_type',
        'language',
        'yatra',
        'event',
    )

    list_editable = ('is_active', 'order')
    search_fields = ('title', 'subtitle')
