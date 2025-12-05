
from django.contrib import admin
from django.urls import path
from userProfile.views import *
from .views import *

urlpatterns = [
    path('list/', YatraListView.as_view(), name='yatra-list'),

]