"""
API ViewSets para la aplicación AUB Bridge.
Expone endpoints REST para jugadores, torneos, parejas y resultados.
"""

from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Q

from .models import (
    Jugador, Torneo, ParejaTorneo,
    ResultadoImportado, RankingImportado, ManoJugada,
)
from .serializers import (
    JugadorSerializer, JugadorResumenSerializer,
    TorneoListSerializer, TorneoDetalleSerializer,
    ParejaTorneoSerializer,
    ResultadoImportadoSerializer,
    RankingImportadoSerializer,
    ManoJugadaSerializer,
)
from .algorithm import equilibrar_parejas


class JugadorViewSet(viewsets.ModelViewSet):
    """
    API endpoint para gestionar jugadores.

    Soporta CRUD completo, búsqueda y filtrado.
    """
    serializer_class = JugadorSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['nombre', 'apellido', 'categoria']
    ordering_fields = ['apellido', 'nombre', 'handicap', 'puntos', 'categoria']
    ordering = ['apellido', 'nombre']
    filterset_fields = ['activo', 'categoria']

    def get_queryset(self):
        """Filtra por jugadores activos por defecto."""
        queryset = Jugador.objects.all()
        activo = self.request.query_params.get('activo', 'true')
        if activo.lower() == 'true':
            queryset = queryset.filter(activo=True)
        return queryset

    @action(detail=False, methods=['get'])
    def buscar(self, request):
        """Endpoint de búsqueda rápida para autocompletado."""
        query = request.query_params.get('q', '').strip()
        torneo_id = request.query_params.get('torneo_id')
        excluir = request.query_params.getlist('excluir')

        if len(query) < 1:
            return Response({'jugadores': []})

        jugadores = Jugador.objects.filter(activo=True).filter(
            Q(nombre__icontains=query) | Q(apellido__icontains=query)
        ).order_by('apellido', 'nombre')[:15]

        # Excluir jugadores ya en parejas del torneo
        if torneo_id:
            try:
                torneo = Torneo.objects.get(id=torneo_id)
                ids_en_parejas = set()
                for pareja in torneo.parejas.all():
                    ids_en_parejas.add(pareja.jugador1_id)
                    ids_en_parejas.add(pareja.jugador2_id)
                jugadores = [j for j in jugadores if j.id not in ids_en_parejas]
            except Torneo.DoesNotExist:
                pass

        # Excluir IDs específicos
        if excluir:
            excluir_set = {int(i) for i in excluir if i.isdigit()}
            jugadores = [j for j in jugadores if j.id not in excluir_set]

        serializer = JugadorResumenSerializer(jugadores[:10], many=True)
        return Response({'jugadores': serializer.data})

    def perform_destroy(self, instance):
        """Soft delete: desactiva el jugador en vez de eliminarlo."""
        instance.activo = False
        instance.save()


class TorneoViewSet(viewsets.ModelViewSet):
    """
    API endpoint para gestionar torneos.

    Incluye acciones para equilibrar y resetear torneos.
    """
    queryset = Torneo.objects.order_by('-fecha')
    permission_classes = [IsAuthenticatedOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['nombre']
    ordering_fields = ['fecha', 'nombre', 'estado']
    ordering = ['-fecha']
    filterset_fields = ['estado', 'tipo']

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return TorneoDetalleSerializer
        return TorneoListSerializer

    @action(detail=True, methods=['post'])
    def equilibrar(self, request, pk=None):
        """Ejecuta el algoritmo de equilibrado NS/EO."""
        torneo = self.get_object()

        if torneo.parejas.count() < 2:
            return Response(
                {'error': 'Se necesitan al menos 2 parejas para equilibrar.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        datos_parejas = [
            {'id': p.id, 'handicap_pareja': p.handicap_pareja}
            for p in torneo.parejas.all()
        ]

        resultado = equilibrar_parejas(datos_parejas)

        ns_ids = {p['id'] for p in resultado['ns']}
        eo_ids = {p['id'] for p in resultado['eo']}

        for pareja in torneo.parejas.all():
            if pareja.id in ns_ids:
                pareja.direccion = 'NS'
            elif pareja.id in eo_ids:
                pareja.direccion = 'EO'
            pareja.save()

        torneo.estado = 'equilibrado'
        torneo.save()

        return Response({
            'status': 'equilibrado',
            'ns_promedio': resultado['ns_promedio'],
            'eo_promedio': resultado['eo_promedio'],
            'diferencia': resultado['diferencia'],
        })

    @action(detail=True, methods=['post'])
    def reset(self, request, pk=None):
        """Resetea el equilibrado del torneo."""
        torneo = self.get_object()
        torneo.estado = 'configuracion'
        torneo.save()

        for pareja in torneo.parejas.all():
            pareja.direccion = None
            pareja.save()

        return Response({'status': 'reseteado'})


class ParejaTorneoViewSet(viewsets.ModelViewSet):
    """
    API endpoint para gestionar parejas de torneo.
    """
    serializer_class = ParejaTorneoSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        torneo_id = self.kwargs.get('torneo_pk')
        if torneo_id:
            return ParejaTorneo.objects.filter(torneo_id=torneo_id)
        return ParejaTorneo.objects.all()

    def perform_create(self, serializer):
        torneo_id = self.kwargs.get('torneo_pk')
        if torneo_id:
            serializer.save(torneo_id=torneo_id)
        else:
            serializer.save()


class ResultadoImportadoViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint de solo lectura para resultados importados.
    """
    serializer_class = ResultadoImportadoSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        torneo_id = self.kwargs.get('torneo_pk')
        if torneo_id:
            return ResultadoImportado.objects.filter(torneo_id=torneo_id)
        return ResultadoImportado.objects.all()


class ManoJugadaViewSet(viewsets.ReadOnlyModelViewSet):
    """
    API endpoint de solo lectura para manos jugadas.
    """
    serializer_class = ManoJugadaSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['board_numero']
    ordering_fields = ['board_numero', 'mp_ns']
    ordering = ['board_numero', '-mp_ns']

    def get_queryset(self):
        resultado_id = self.kwargs.get('resultado_pk')
        if resultado_id:
            return ManoJugada.objects.filter(resultado_id=resultado_id)
        return ManoJugada.objects.all()
