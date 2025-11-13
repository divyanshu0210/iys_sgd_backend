from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView, SpectacularRedocView
from userProfile.confirm_email import CustomConfirmEmailView
from dj_rest_auth.registration.views import SocialLoginView
from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from django.conf import settings
from django.conf.urls.static import static
class GoogleLogin(SocialLoginView):
    adapter_class = GoogleOAuth2Adapter




urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('userProfile.urls')),  # Include app URLs
    path('yatras/', include('yatra.urls')),  # Yatra app URLs
    path('payments/', include('payment.urls')),  # Payment app URLs

      # Auth APIs
    path('api/auth/', include('dj_rest_auth.urls')),  # login/logout/password reset/change
    path('api/auth/register/', include('dj_rest_auth.registration.urls')), 
     # Auth APIs
    path('api/auth/registration/', include('dj_rest_auth.registration.urls')),  # registration & email verification # register + verify email
    path('api/auth/registration/social/login/', GoogleLogin.as_view(), name='google_login'),  # social login
     path('api/auth/account-confirm-email/<key>/', CustomConfirmEmailView.as_view(), name='account_confirm_email'),
        # 👇 or this one (either works)
    path('auth/', include('django.contrib.auth.urls')),
      # social login



      # ✅ API schema generator
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),

    # ✅ Swagger UI
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),

    # ✅ Redoc UI
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]+ static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
