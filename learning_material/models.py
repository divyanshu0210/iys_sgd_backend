from django.db import models

from yatra.models import Yatra
from announcements.models import *

class Resource(models.Model):
    RESOURCE_TYPES = [
        ('pdf', 'PDF'),
        ('audio', 'Audio'),
        ('video', 'Video'),
        ('youtube', 'YouTube'),
    ]

    LANGUAGES = [
        ('hi', 'Hindi'),
        ('en', 'English'),
        ('mr', 'Marathi'),
        ('kn', 'Kannada'),
    ]

    CATEGORIES = [
        ('lecture', 'Lecture'),
        ('kirtan', 'Kirtan'),
        ('reading', 'Reading Material'),
        ('guideline', 'Guidelines'),
        ('instruction', 'Instructions'),
        ('other', 'Other'),
    ]

    title = models.CharField(max_length=255)
    subtitle = models.CharField(max_length=500, blank=True)

    thumbnail = models.ImageField(
        upload_to='resource_thumbnails/',
        blank=True,
        null=True
    )

    category = models.CharField(
        max_length=30,
        choices=CATEGORIES,
        default='other'
    )

    resource_type = models.CharField(
        max_length=20,
        choices=RESOURCE_TYPES
    )

    language = models.CharField(
        max_length=10,
        choices=LANGUAGES
    )

    link_url = models.URLField(
        help_text="Google Drive / YouTube / External link"
    )

    yatra = models.ForeignKey(
        Yatra,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name='resources'
    )

    event = models.ForeignKey(
        Event,
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name='resources'
    )

    is_active = models.BooleanField(default=True)
    order = models.PositiveIntegerField(default=0)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['order', '-created_at']
