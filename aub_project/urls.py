"""
URL configuration for aub_project project.
"""
from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)

urlpatterns = [
    path('admin/', admin.site.urls),

    # API REST (DRF)
    path('api/', include('bridge.api_urls')),

    # JWT Authentication endpoints
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # Auth0 Social Auth
    path('auth/', include('social_django.urls', namespace='social')),

    # DRF browsable API login (development)
    path('api-auth/', include('rest_framework.urls')),

    # Frontend views
    path('', include('bridge.urls')),
]
