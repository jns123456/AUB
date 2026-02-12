"""
Modelos de la base de datos para la aplicación AUB Bridge.
"""

from django.db import models
from datetime import date


class Jugador(models.Model):
    """Modelo de jugador de bridge con su handicap y datos de ranking."""

    nombre = models.CharField(max_length=100)
    apellido = models.CharField(max_length=100)
    handicap = models.FloatField(default=0)
    puntos = models.FloatField(null=True, blank=True, default=0)
    cn_totales = models.IntegerField(null=True, blank=True, default=0)
    categoria = models.CharField(max_length=50, null=True, blank=True, default='')
    activo = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'jugadores'
        ordering = ['apellido', 'nombre']

    def __str__(self):
        return f'{self.nombre} {self.apellido} (HC: {self.handicap})'

    @property
    def nombre_completo(self):
        return f'{self.nombre} {self.apellido}'


class Torneo(models.Model):
    """Modelo de torneo de bridge."""

    ESTADO_CHOICES = [
        ('configuracion', 'Configuración'),
        ('equilibrado', 'Equilibrado'),
    ]

    nombre = models.CharField(max_length=200)
    fecha = models.DateField(default=date.today)
    tipo = models.CharField(max_length=50, null=True, blank=True, default='handicap')
    estado = models.CharField(max_length=20, choices=ESTADO_CHOICES, default='configuracion')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'torneos'
        ordering = ['-fecha']

    def __str__(self):
        return f'{self.nombre} ({self.fecha})'

    @property
    def cantidad_parejas(self):
        return self.parejas.count()

    @property
    def parejas_ns(self):
        return self.parejas.filter(direccion='NS')

    @property
    def parejas_eo(self):
        return self.parejas.filter(direccion='EO')


class ParejaTorneo(models.Model):
    """Modelo de pareja inscrita en un torneo."""

    DIRECCION_CHOICES = [
        ('NS', 'Norte-Sur'),
        ('EO', 'Este-Oeste'),
    ]

    torneo = models.ForeignKey(Torneo, on_delete=models.CASCADE, related_name='parejas')
    jugador1 = models.ForeignKey(Jugador, on_delete=models.CASCADE, related_name='parejas_como_j1')
    jugador2 = models.ForeignKey(Jugador, on_delete=models.CASCADE, related_name='parejas_como_j2')
    direccion = models.CharField(max_length=2, choices=DIRECCION_CHOICES, null=True, blank=True)
    handicap_pareja = models.FloatField()
    posicion_final = models.IntegerField(null=True, blank=True)
    porcentaje = models.FloatField(null=True, blank=True)
    puntos_ranking = models.FloatField(null=True, blank=True, default=0)

    class Meta:
        db_table = 'parejas_torneo'

    def __str__(self):
        return f'{self.jugador1.nombre_completo} & {self.jugador2.nombre_completo} (HC: {self.handicap_pareja})'

    def calcular_handicap(self):
        """Calcula el handicap promedio de la pareja."""
        self.handicap_pareja = round((self.jugador1.handicap + self.jugador2.handicap) / 2, 2)
        return self.handicap_pareja


class ResultadoImportado(models.Model):
    """Modelo para guardar los resultados importados de un torneo desde archivos externos."""

    torneo = models.OneToOneField(Torneo, on_delete=models.CASCADE, related_name='resultado_importado')
    nombre_archivo_ranks = models.CharField(max_length=255, null=True, blank=True)
    nombre_archivo_travellers = models.CharField(max_length=255, null=True, blank=True)
    fecha_importacion = models.DateTimeField(auto_now_add=True)
    session_info = models.CharField(max_length=200, null=True, blank=True)
    mesas = models.IntegerField(null=True, blank=True)
    boards_totales = models.IntegerField(null=True, blank=True)
    movimiento = models.CharField(max_length=100, null=True, blank=True)

    class Meta:
        db_table = 'resultados_importados'

    def __str__(self):
        return f'Resultado de {self.torneo.nombre}'


class RankingImportado(models.Model):
    """Modelo para guardar el ranking de cada pareja en un torneo importado."""

    resultado = models.ForeignKey(ResultadoImportado, on_delete=models.CASCADE, related_name='rankings')
    posicion = models.IntegerField()
    numero_pareja = models.IntegerField()
    nombre_jugador1 = models.CharField(max_length=150)
    nombre_jugador2 = models.CharField(max_length=150)
    boards_jugados = models.IntegerField(null=True, blank=True)
    total_puntos = models.FloatField(null=True, blank=True)
    maximo_puntos = models.IntegerField(null=True, blank=True)
    porcentaje = models.FloatField(null=True, blank=True)
    handicap = models.FloatField(null=True, blank=True)
    porcentaje_con_handicap = models.FloatField(null=True, blank=True)
    puntos_asignados = models.FloatField(null=True, blank=True, default=0)

    # Relaciones opcionales con jugadores si se pueden emparejar
    jugador1 = models.ForeignKey(Jugador, on_delete=models.SET_NULL, null=True, blank=True, related_name='rankings_como_j1')
    jugador2 = models.ForeignKey(Jugador, on_delete=models.SET_NULL, null=True, blank=True, related_name='rankings_como_j2')

    class Meta:
        db_table = 'rankings_importados'
        ordering = ['posicion']

    def __str__(self):
        return f'#{self.posicion}: {self.nombre_jugador1} & {self.nombre_jugador2}'


class ManoJugada(models.Model):
    """Modelo para guardar cada mano/board jugada en un torneo."""

    resultado = models.ForeignKey(ResultadoImportado, on_delete=models.CASCADE, related_name='manos')
    board_numero = models.IntegerField()
    pareja_ns = models.IntegerField(null=True, blank=True)
    pareja_ew = models.IntegerField(null=True, blank=True)
    contrato = models.CharField(max_length=20, null=True, blank=True)
    declarante = models.CharField(max_length=5, null=True, blank=True)
    salida = models.CharField(max_length=10, null=True, blank=True)
    puntos_ns_positivo = models.IntegerField(null=True, blank=True)
    puntos_ns_negativo = models.IntegerField(null=True, blank=True)
    mp_ns = models.FloatField(null=True, blank=True)
    mp_ew = models.FloatField(null=True, blank=True)
    nombre_pareja_ns = models.CharField(max_length=200, null=True, blank=True)
    nombre_pareja_ew = models.CharField(max_length=200, null=True, blank=True)

    class Meta:
        db_table = 'manos_jugadas'
        ordering = ['board_numero', '-mp_ns']

    def __str__(self):
        return f'Board {self.board_numero}: {self.contrato} por {self.declarante}'

    @property
    def puntos_ns(self):
        """Devuelve los puntos NS (positivo o negativo)."""
        if self.puntos_ns_positivo:
            return self.puntos_ns_positivo
        elif self.puntos_ns_negativo:
            return -self.puntos_ns_negativo
        return 0
