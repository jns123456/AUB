"""
URLs de la API REST para la aplicación Bridge.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .api_views import (
    JugadorViewSet,
    TorneoViewSet,
    ParejaTorneoViewSet,
    ResultadoImportadoViewSet,
    ManoJugadaViewSet,
)

router = DefaultRouter()
router.register(r'jugadores', JugadorViewSet, basename='api-jugador')
router.register(r'torneos', TorneoViewSet, basename='api-torneo')
router.register(r'parejas', ParejaTorneoViewSet, basename='api-pareja')
router.register(r'resultados', ResultadoImportadoViewSet, basename='api-resultado')
router.register(r'manos', ManoJugadaViewSet, basename='api-mano')

urlpatterns = [
    path('', include(router.urls)),
]
