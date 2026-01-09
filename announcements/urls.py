from django.urls import path
from .views import *

urlpatterns = [
    path("events/home/", EventsAPIView.as_view(), name="home-events"),
    path("events/", AllEventListAPIView.as_view(), name="event-list"),
    path("events/live/", LiveEventsAPIView.as_view(), name="live-events"),
    path("events/<int:pk>/", EventDetailAPIView.as_view(), name="event-detail"),
]
