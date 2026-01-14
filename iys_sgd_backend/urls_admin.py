from django.contrib import admin
from django.urls import path, include
from yatra_registration.views import MarkAttendanceView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('_nested_admin/', include('nested_admin.urls')),
    path('mark-attendance/<uuid:registration_id>/', MarkAttendanceView.as_view(), name='mark-attendance'),
]

