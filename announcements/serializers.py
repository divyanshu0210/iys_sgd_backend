from rest_framework import serializers
from .models import Event


class EventSerializer(serializers.ModelSerializer):

    class Meta:
        model = Event
        fields = [
            "id",
            "title",
            "description",
            "poster",
            "event_type",
            "status",
            "start_datetime",
            "end_datetime",
            "youtube_live_url",
            "youtube_replay_url",
            "youtube_thumbnail",
            "location_name",
            "location_map_link",
            "registration_link",
            "is_active",
            "created_at",]


