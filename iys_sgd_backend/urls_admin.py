from django.contrib import admin
from django.urls import path, include
from payment.views import keep_alive

urlpatterns = [
    path('admin/', admin.site.urls),
    path('_nested_admin/', include('nested_admin.urls')),
    path('check/', keep_alive),
]
