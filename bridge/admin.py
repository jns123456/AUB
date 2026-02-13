"""
Configuración del admin de Django para la aplicación Bridge.
"""

from django.contrib import admin
from .models import Jugador, Torneo, ParejaTorneo, Lugar


@admin.register(Jugador)
class JugadorAdmin(admin.ModelAdmin):
    list_display = ['apellido', 'nombre', 'handicap', 'categoria', 'puntos', 'cn_totales', 'es_director', 'activo']
    list_filter = ['activo', 'categoria', 'es_director']
    search_fields = ['nombre', 'apellido']
    ordering = ['apellido', 'nombre']


@admin.register(Lugar)
class LugarAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'activo']
    list_filter = ['activo']
    search_fields = ['nombre']


@admin.register(Torneo)
class TorneoAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'fecha', 'tipo', 'estado', 'director', 'lugar', 'cantidad_parejas']
    list_filter = ['estado', 'tipo', 'lugar']
    search_fields = ['nombre']
    ordering = ['-fecha']


@admin.register(ParejaTorneo)
class ParejaTorneoAdmin(admin.ModelAdmin):
    list_display = ['torneo', 'jugador1', 'jugador2', 'direccion', 'handicap_pareja', 'posicion_final', 'puntos_ranking']
    list_filter = ['torneo', 'direccion']
    search_fields = ['jugador1__nombre', 'jugador1__apellido', 'jugador2__nombre', 'jugador2__apellido']
