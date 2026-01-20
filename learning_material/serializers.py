# content/serializers.py
from rest_framework import serializers
from .models import Resource

class ResourceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Resource
        fields = [
            'id',
            'title',
            'subtitle',
            'thumbnail',
            'resource_type',
            'category',
            'language',
            'link_url',
            'yatra',
            'event',
            'order',
        ]
