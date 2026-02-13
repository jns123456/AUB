"""
Serializers para la API REST de la aplicación AUB Bridge.
"""

from rest_framework import serializers
from .models import Jugador, Torneo, ParejaTorneo, ResultadoImportado, RankingImportado, ManoJugada


class JugadorSerializer(serializers.ModelSerializer):
    """Serializer completo para el modelo Jugador."""
    nombre_completo = serializers.ReadOnlyField()

    class Meta:
        model = Jugador
        fields = [
            'id', 'nombre', 'apellido', 'nombre_completo',
            'handicap', 'puntos', 'cn_totales', 'categoria',
            'activo', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class JugadorResumenSerializer(serializers.ModelSerializer):
    """Serializer resumido para listados y referencias."""

    class Meta:
        model = Jugador
        fields = ['id', 'nombre', 'apellido', 'handicap']


class ParejaTorneoSerializer(serializers.ModelSerializer):
    """Serializer para parejas dentro de un torneo."""
    jugador1 = JugadorResumenSerializer(read_only=True)
    jugador2 = JugadorResumenSerializer(read_only=True)
    jugador1_id = serializers.PrimaryKeyRelatedField(
        queryset=Jugador.objects.filter(activo=True),
        source='jugador1',
        write_only=True,
    )
    jugador2_id = serializers.PrimaryKeyRelatedField(
        queryset=Jugador.objects.filter(activo=True),
        source='jugador2',
        write_only=True,
    )

    class Meta:
        model = ParejaTorneo
        fields = [
            'id', 'torneo', 'jugador1', 'jugador2',
            'jugador1_id', 'jugador2_id',
            'direccion', 'handicap_pareja',
            'posicion_final', 'porcentaje', 'puntos_ranking',
        ]
        read_only_fields = ['id', 'handicap_pareja']

    def validate(self, data):
        """Valida que los dos jugadores sean diferentes."""
        jugador1 = data.get('jugador1')
        jugador2 = data.get('jugador2')
        if jugador1 and jugador2 and jugador1.id == jugador2.id:
            raise serializers.ValidationError(
                'Los dos jugadores de la pareja deben ser diferentes.'
            )
        return data

    def create(self, validated_data):
        """Calcula el handicap de la pareja al crearla."""
        jugador1 = validated_data['jugador1']
        jugador2 = validated_data['jugador2']
        validated_data['handicap_pareja'] = round(
            (jugador1.handicap + jugador2.handicap) / 2, 2
        )
        return super().create(validated_data)


class TorneoListSerializer(serializers.ModelSerializer):
    """Serializer para listado de torneos."""
    cantidad_parejas = serializers.ReadOnlyField()

    class Meta:
        model = Torneo
        fields = [
            'id', 'nombre', 'fecha', 'tipo', 'estado',
            'cantidad_parejas', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class TorneoDetalleSerializer(serializers.ModelSerializer):
    """Serializer detallado para un torneo con sus parejas."""
    parejas = ParejaTorneoSerializer(many=True, read_only=True)
    cantidad_parejas = serializers.ReadOnlyField()

    class Meta:
        model = Torneo
        fields = [
            'id', 'nombre', 'fecha', 'tipo', 'estado',
            'cantidad_parejas', 'parejas', 'created_at',
        ]
        read_only_fields = ['id', 'created_at']


class RankingImportadoSerializer(serializers.ModelSerializer):
    """Serializer para rankings importados."""
    jugador1 = JugadorResumenSerializer(read_only=True)
    jugador2 = JugadorResumenSerializer(read_only=True)

    class Meta:
        model = RankingImportado
        fields = [
            'id', 'posicion', 'numero_pareja',
            'nombre_jugador1', 'nombre_jugador2',
            'boards_jugados', 'total_puntos', 'maximo_puntos',
            'porcentaje', 'handicap', 'porcentaje_con_handicap',
            'puntos_asignados', 'jugador1', 'jugador2',
        ]


class ManoJugadaSerializer(serializers.ModelSerializer):
    """Serializer para manos jugadas."""
    puntos_ns = serializers.ReadOnlyField()

    class Meta:
        model = ManoJugada
        fields = [
            'id', 'board_numero', 'pareja_ns', 'pareja_ew',
            'contrato', 'declarante', 'salida',
            'puntos_ns_positivo', 'puntos_ns_negativo', 'puntos_ns',
            'mp_ns', 'mp_ew',
            'nombre_pareja_ns', 'nombre_pareja_ew',
        ]


class ResultadoImportadoSerializer(serializers.ModelSerializer):
    """Serializer para resultados importados con rankings."""
    rankings = RankingImportadoSerializer(many=True, read_only=True)

    class Meta:
        model = ResultadoImportado
        fields = [
            'id', 'torneo', 'nombre_archivo_ranks',
            'nombre_archivo_travellers', 'fecha_importacion',
            'session_info', 'mesas', 'boards_totales',
            'movimiento', 'rankings',
        ]
