from django.urls import path
from .views import ResourceListAPIView

urlpatterns = [
    path('resources/', ResourceListAPIView.as_view(), name='resource-list'),
]