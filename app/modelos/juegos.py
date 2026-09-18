import enum
from sqlalchemy import Column, Integer, String, Float, DateTime, Enum, ForeignKey
from sqlalchemy.sql import func

from app.core.database import Base


class ModuloJuego(str, enum.Enum):
    CLASICO = "clasico"      # jugadas directas, premio por tabla de pago
    RIFA = "rifa"            # numeros pre-soldados, premio fijo
    SEMANAL = "semanal"      # pozo acumulado que se reparte entre ganadores


class EstadoSorteo(str, enum.Enum):
    PROGRAMADO = "programado"    # acepta jugadas
    CERRADO = "cerrado"          # no acepta mas jugadas, espera resultado
    LIQUIDADO = "liquidado"      # resultado cargado y premios calculados


class EstadoJugada(str, enum.Enum):
    PENDIENTE = "pendiente"
    APROBADA = "aprobada"
    RECHAZADA = "rechazada"
    GANADORA = "ganadora"
    PERDEDORA = "perdedora"


class Sorteo(Base):
    """Edicion de un juego: una fecha y un modulo concretos."""
    __tablename__ = "sorteos"

    id = Column(Integer, primary_key=True, index=True)
    modulo = Column(Enum(ModuloJuego, name="modulo_juego"), nullable=False)
    fecha_sorteo = Column(DateTime(timezone=True), nullable=False)
    estado = Column(Enum(EstadoSorteo, name="estado_sorteo"), default=EstadoSorteo.PROGRAMADO)
    resultado_numero = Column(Integer, nullable=True)
    premio_fijo = Column(Float, nullable=True)     # Solo rifa: premio al ticket ganador
    pozo_acumulado = Column(Float, default=0.0)    # Semanal: arrastre de semanas sin ganador
    creado_en = Column(DateTime(timezone=True), server_default=func.now())


class Jugada(Base):
    """Apuesta cargada por un revendedor para un sorteo."""
    __tablename__ = "jugadas"

    id = Column(Integer, primary_key=True, index=True)
    sorteo_id = Column(Integer, ForeignKey("sorteos.id"), nullable=False)
    revendedor_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    jugador_nombre = Column(String(100), nullable=True)
    numero = Column(Integer, nullable=False)
    monto = Column(Float, nullable=False)
    estado = Column(Enum(EstadoJugada, name="estado_jugada"), default=EstadoJugada.PENDIENTE)
    premio = Column(Float, nullable=True)
    comision_pct = Column(Float, nullable=True)     # Foto del % al aprobar
    comision_monto = Column(Float, nullable=True)
    creada_en = Column(DateTime(timezone=True), server_default=func.now())
