from django.shortcuts import render

# Create your views here.
from rest_framework.generics import ListAPIView
from django.utils import timezone
from .models import Event
from .serializers import EventSerializer
from rest_framework.generics import RetrieveAPIView
from rest_framework.permissions import IsAuthenticated, IsAdminUser, AllowAny



class EventsAPIView(ListAPIView):
    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()]
        return [IsAdminUser()]
    serializer_class = EventSerializer

    def get_queryset(self):
        return Event.objects.filter(
            is_active=True,
            status__in=["upcoming", "live"]
        ).order_by("start_datetime")
    
class AllEventListAPIView(ListAPIView):
    queryset = Event.objects.filter(is_active=True).order_by("-start_datetime")
    serializer_class = EventSerializer


class EventDetailAPIView(RetrieveAPIView):
    queryset = Event.objects.filter(is_active=True)
    serializer_class = EventSerializer

class LiveEventsAPIView(ListAPIView):
    serializer_class = EventSerializer

    def get_queryset(self):
        return Event.objects.filter(
            is_active=True,
            status="live"
        ).order_by("start_datetime")