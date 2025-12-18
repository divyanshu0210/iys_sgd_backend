from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView
from dj_rest_auth.registration.views import SocialLoginView
from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from django.conf import settings
from yatra_auth.views import *
from yatra_auth.views import CustomConfirmEmailView
class GoogleLogin(SocialLoginView):
    adapter_class = GoogleOAuth2Adapter




urlpatterns = [
    path('api/', include('userProfile.urls')),  # Include app URLs
    path('yatra/', include('yatra.urls')),  # Yatra app URLs
    path('yatras/', include('yatra_registration.urls')),  # Yatra app URLs
    path('payments/', include('payment.urls')),  # Payment app URLs
    path('yatra-transfers/', include('yatra_substitution.urls')),  # Payment app URLs

      # Auth APIs
    path('api/auth/', include('dj_rest_auth.urls')),  # login/logout/password reset/change
    path('api/auth/register/', include('dj_rest_auth.registration.urls')), 
    path('api/auth/registration/', include('dj_rest_auth.registration.urls')),  # registration & email verification # register + verify emai
    path('api/auth/registration/social/login/', GoogleLogin.as_view(), name='google_login'),  # social login
     path('api/auth/account-confirm-email/<key>/', CustomConfirmEmailView.as_view(), name='account_confirm_email'),

    path('api/yatra_auth/', include('yatra_auth.urls')),



      # ✅ API schema generator
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),

    # ✅ Swagger UI
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),

    # ✅ Redoc UI
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]

# + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
