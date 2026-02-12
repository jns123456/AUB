"""
Modelos de la base de datos para la aplicación AUB Bridge.
"""

from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date

db = SQLAlchemy()


class Jugador(db.Model):
    """Modelo de jugador de bridge con su handicap y datos de ranking."""

    __tablename__ = 'jugadores'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    apellido = db.Column(db.String(100), nullable=False)
    handicap = db.Column(db.Float, nullable=False, default=0)
    puntos = db.Column(db.Float, nullable=True, default=0)
    cn_totales = db.Column(db.Integer, nullable=True, default=0)
    categoria = db.Column(db.String(50), nullable=True, default='')
    activo = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Jugador {self.nombre} {self.apellido} (HC: {self.handicap})>'

    @property
    def nombre_completo(self):
        return f'{self.nombre} {self.apellido}'


class Torneo(db.Model):
    """Modelo de torneo de bridge."""

    __tablename__ = 'torneos'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(200), nullable=False)
    fecha = db.Column(db.Date, nullable=False, default=date.today)
    tipo = db.Column(db.String(50), nullable=True, default='handicap')
    estado = db.Column(db.String(20), default='configuracion')  # configuracion, equilibrado
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    parejas = db.relationship('ParejaTorneo', backref='torneo', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Torneo {self.nombre} ({self.fecha})>'

    @property
    def cantidad_parejas(self):
        return len(self.parejas)

    @property
    def parejas_ns(self):
        return [p for p in self.parejas if p.direccion == 'NS']

    @property
    def parejas_eo(self):
        return [p for p in self.parejas if p.direccion == 'EO']


class ParejaTorneo(db.Model):
    """Modelo de pareja inscrita en un torneo."""

    __tablename__ = 'parejas_torneo'

    id = db.Column(db.Integer, primary_key=True)
    torneo_id = db.Column(db.Integer, db.ForeignKey('torneos.id'), nullable=False)
    jugador1_id = db.Column(db.Integer, db.ForeignKey('jugadores.id'), nullable=False)
    jugador2_id = db.Column(db.Integer, db.ForeignKey('jugadores.id'), nullable=False)
    direccion = db.Column(db.String(2), nullable=True)  # NS, EO, o null (sin asignar)
    handicap_pareja = db.Column(db.Float, nullable=False)
    posicion_final = db.Column(db.Integer, nullable=True)
    porcentaje = db.Column(db.Float, nullable=True)  # % obtenido en el torneo
    puntos_ranking = db.Column(db.Float, nullable=True, default=0)

    jugador1 = db.relationship('Jugador', foreign_keys=[jugador1_id])
    jugador2 = db.relationship('Jugador', foreign_keys=[jugador2_id])

    def __repr__(self):
        return f'<Pareja {self.jugador1.nombre_completo} & {self.jugador2.nombre_completo} (HC: {self.handicap_pareja})>'

    def calcular_handicap(self):
        """Calcula el handicap promedio de la pareja."""
        self.handicap_pareja = round((self.jugador1.handicap + self.jugador2.handicap) / 2, 2)
        return self.handicap_pareja


class ResultadoImportado(db.Model):
    """Modelo para guardar los resultados importados de un torneo desde archivos externos."""

    __tablename__ = 'resultados_importados'

    id = db.Column(db.Integer, primary_key=True)
    torneo_id = db.Column(db.Integer, db.ForeignKey('torneos.id'), nullable=False)
    nombre_archivo_ranks = db.Column(db.String(255), nullable=True)
    nombre_archivo_travellers = db.Column(db.String(255), nullable=True)
    fecha_importacion = db.Column(db.DateTime, default=datetime.utcnow)
    session_info = db.Column(db.String(200), nullable=True)  # "Session 1 Section A"
    mesas = db.Column(db.Integer, nullable=True)
    boards_totales = db.Column(db.Integer, nullable=True)
    movimiento = db.Column(db.String(100), nullable=True)  # "Howell", "Mitchell", etc.

    torneo = db.relationship('Torneo', backref=db.backref('resultado_importado', uselist=False))
    rankings = db.relationship('RankingImportado', backref='resultado', lazy=True, cascade='all, delete-orphan')
    manos = db.relationship('ManoJugada', backref='resultado', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<ResultadoImportado torneo={self.torneo_id}>'


class RankingImportado(db.Model):
    """Modelo para guardar el ranking de cada pareja en un torneo importado."""

    __tablename__ = 'rankings_importados'

    id = db.Column(db.Integer, primary_key=True)
    resultado_id = db.Column(db.Integer, db.ForeignKey('resultados_importados.id'), nullable=False)
    posicion = db.Column(db.Integer, nullable=False)
    numero_pareja = db.Column(db.Integer, nullable=False)
    nombre_jugador1 = db.Column(db.String(150), nullable=False)
    nombre_jugador2 = db.Column(db.String(150), nullable=False)
    boards_jugados = db.Column(db.Integer, nullable=True)
    total_puntos = db.Column(db.Float, nullable=True)
    maximo_puntos = db.Column(db.Integer, nullable=True)
    porcentaje = db.Column(db.Float, nullable=True)
    handicap = db.Column(db.Float, nullable=True)
    porcentaje_con_handicap = db.Column(db.Float, nullable=True)
    puntos_asignados = db.Column(db.Float, nullable=True, default=0)  # Puntos de ranking asignados

    # Relaciones opcionales con jugadores si se pueden emparejar
    jugador1_id = db.Column(db.Integer, db.ForeignKey('jugadores.id'), nullable=True)
    jugador2_id = db.Column(db.Integer, db.ForeignKey('jugadores.id'), nullable=True)

    jugador1 = db.relationship('Jugador', foreign_keys=[jugador1_id])
    jugador2 = db.relationship('Jugador', foreign_keys=[jugador2_id])

    def __repr__(self):
        return f'<RankingImportado #{self.posicion}: {self.nombre_jugador1} & {self.nombre_jugador2}>'


class ManoJugada(db.Model):
    """Modelo para guardar cada mano/board jugada en un torneo."""

    __tablename__ = 'manos_jugadas'

    id = db.Column(db.Integer, primary_key=True)
    resultado_id = db.Column(db.Integer, db.ForeignKey('resultados_importados.id'), nullable=False)
    board_numero = db.Column(db.Integer, nullable=False)
    pareja_ns = db.Column(db.Integer, nullable=True)  # Número de pareja NS
    pareja_ew = db.Column(db.Integer, nullable=True)  # Número de pareja EW
    contrato = db.Column(db.String(20), nullable=True)  # "4S", "3NT", "5Dx", etc.
    declarante = db.Column(db.String(5), nullable=True)  # "N", "S", "E", "W"
    salida = db.Column(db.String(10), nullable=True)  # Lead
    puntos_ns_positivo = db.Column(db.Integer, nullable=True)  # NS+
    puntos_ns_negativo = db.Column(db.Integer, nullable=True)  # NS-
    mp_ns = db.Column(db.Float, nullable=True)  # Match Points NS
    mp_ew = db.Column(db.Float, nullable=True)  # Match Points EW
    nombre_pareja_ns = db.Column(db.String(200), nullable=True)
    nombre_pareja_ew = db.Column(db.String(200), nullable=True)

    def __repr__(self):
        return f'<ManoJugada Board {self.board_numero}: {self.contrato} por {self.declarante}>'

    @property
    def puntos_ns(self):
        """Devuelve los puntos NS (positivo o negativo)."""
        if self.puntos_ns_positivo:
            return self.puntos_ns_positivo
        elif self.puntos_ns_negativo:
            return -self.puntos_ns_negativo
        return 0
