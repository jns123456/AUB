"""
URLs de la aplicación Bridge.
"""

from django.urls import path
from . import views

urlpatterns = [
    # Página principal
    path('', views.index, name='index'),
    
    # Jugadores
    path('jugadores/', views.jugadores, name='jugadores'),
    path('jugadores/nuevo/', views.jugador_nuevo, name='jugador_nuevo'),
    path('jugadores/<int:id>/editar/', views.jugador_editar, name='jugador_editar'),
    path('jugadores/<int:id>/eliminar/', views.jugador_eliminar, name='jugador_eliminar'),
    path('jugadores/eliminar-todos/', views.jugadores_eliminar_todos, name='jugadores_eliminar_todos'),
    path('jugadores/importar/', views.jugadores_importar, name='jugadores_importar'),
    path('api/jugadores/buscar/', views.api_buscar_jugadores, name='api_buscar_jugadores'),
    
    # Cargar base de handicaps
    path('cargar-base/', views.cargar_base, name='cargar_base'),
    path('cargar-base/confirmar/', views.cargar_base_confirmar, name='cargar_base_confirmar'),
    
    # Torneos
    path('torneos/', views.torneos, name='torneos'),
    path('torneo/nuevo/', views.torneo_nuevo, name='torneo_nuevo'),
    path('torneo/<int:id>/', views.torneo_detalle, name='torneo_detalle'),
    path('torneo/<int:id>/pareja/', views.torneo_agregar_pareja, name='torneo_agregar_pareja'),
    path('torneo/<int:id>/pareja/<int:pareja_id>/eliminar/', views.torneo_eliminar_pareja, name='torneo_eliminar_pareja'),
    path('torneo/<int:id>/equilibrar/', views.torneo_equilibrar, name='torneo_equilibrar'),
    path('torneo/<int:id>/reset/', views.torneo_reset, name='torneo_reset'),
    path('torneo/<int:id>/resultados/', views.torneo_resultados, name='torneo_resultados'),
    path('torneo/<int:id>/eliminar/', views.torneo_eliminar, name='torneo_eliminar'),
    
    # Ranking
    path('ranking/', views.ranking, name='ranking'),
    path('ranking/<int:anio>/', views.ranking, name='ranking_anio'),
    
    # Importación de resultados
    path('torneo/<int:id>/importar-resultados/', views.torneo_importar_resultados, name='torneo_importar_resultados'),
    path('torneo/<int:id>/resultados-importados/', views.torneo_ver_resultados, name='torneo_ver_resultados'),
    path('torneo/<int:id>/manos/', views.torneo_ver_manos, name='torneo_ver_manos'),
    path('torneo/<int:id>/manos/<int:board>/', views.torneo_ver_manos, name='torneo_ver_manos_board'),
    path('torneo/<int:id>/actualizar-puntos/', views.torneo_actualizar_puntos, name='torneo_actualizar_puntos'),
]
