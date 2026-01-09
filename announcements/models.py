from django.db import models

# Create your models here.
from django.db import models
from django.utils import timezone
import re

class Event(models.Model):
    EVENT_TYPE_CHOICES = [
        ("offline", "Offline"),
        ("online", "Online"),
        ("hybrid", "Hybrid"),
    ]

    STATUS_CHOICES = [
        ("upcoming", "Upcoming"),
        ("live", "Live"),
        ("completed", "Completed"),
    ]

    title = models.CharField(max_length=200)
    description = models.TextField()

    poster = models.ImageField(
        upload_to="events/posters/",
        blank=True,
        null=True
    )

    event_type = models.CharField(
        max_length=10,
        choices=EVENT_TYPE_CHOICES,
        default="offline",
    )

    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default="upcoming",
    )

    start_datetime = models.DateTimeField()
    end_datetime = models.DateTimeField(blank=True, null=True)

    # 🎥 VIDEO
    youtube_live_url = models.URLField(blank=True, null=True)
    youtube_replay_url = models.URLField(blank=True, null=True)
    youtube_thumbnail = models.URLField(blank=True, null=True)

    # 📍 LOCATION
    location_name = models.CharField(max_length=200, blank=True)
    location_map_link = models.URLField(blank=True)

    # 🔗 ACTIONS
    registration_link = models.URLField(blank=True)

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def is_live(self):
        return self.status == "live"

    def __str__(self):
        return self.title
    
    @staticmethod
    def extract_youtube_id(url):
        pattern = r"(?:v=|\/)([0-9A-Za-z_-]{11}).*"
        match = re.search(pattern, url)
        return match.group(1) if match else None
    
    def save(self, *args, **kwargs):
        if self.youtube_live_url and not self.youtube_thumbnail:
            video_id = self.extract_youtube_id(self.youtube_live_url)
            if video_id:
                self.youtube_thumbnail = (
                    f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"
                )
        super().save(*args, **kwargs)



