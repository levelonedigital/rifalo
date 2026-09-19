import enum
from sqlalchemy import Column, Integer, String, Boolean, Float, DateTime, Enum, ForeignKey
from sqlalchemy.sql import func

from app.core.database import Base


class ModuloJuego(str, enum.Enum):
    CLASICO = "clasico"    # 3 numeros, pozo por sorteo de horario
    SEMANAL = "semanal"    # 10 numeros, pozo semanal (5 dias, 1 horario)
    RIFA = "rifa"          # 1 numero, premio fijo


class EstadoSorteo(str, enum.Enum):
    PROGRAMADO = "programado"
    CERRADO = "cerrado"
    LIQUIDADO = "liquidado"


class EstadoJugada(str, enum.Enum):
    PENDIENTE = "pendiente"
    APROBADA = "aprobada"
    RECHAZADA = "rechazada"
    GANADORA = "ganadora"
    PERDEDORA = "perdedora"


class ReglasSistema(Base):
    """Reglas POR DEFECTO (una unica fila, id=1). Cada sorteo puede pisarlas."""
    __tablename__ = "reglas_sistema"

    id = Column(Integer, primary_key=True, default=1)
    precio_clasico = Column(Float, default=200.0)
    precio_semanal = Column(Float, default=500.0)
    precio_rifa = Column(Float, default=100.0)
    pozo_base_clasico = Column(Float, default=100000.0)
    pozo_base_semanal = Column(Float, default=500000.0)
    pozo_pct = Column(Float, default=50.0)
    vendedor_pct = Column(Float, default=20.0)
    horarios = Column(String(300), default='{"matutina":"11:30","vespertina":"14:30","siesta":"17:30","tarde":"19:30","nocturna":"22:00"}')
    semanal_horario = Column(String(20), default="nocturna")
    semanal_dia_inicio = Column(Integer, default=0)
    semanal_dia_fin = Column(Integer, default=4)
    busqueda_inicio_min = Column(Integer, default=1)
    busqueda_intervalo_min = Column(Integer, default=2)
    busqueda_duracion_min = Column(Integer, default=16)

    def dict_horarios(self):
        import json
        try:
            return json.loads(self.horarios or "{}")
        except Exception:
            return {}

    @property
    def casa_pct_por_defecto(self):
        return max(0.0, 100.0 - (self.pozo_pct or 0.0) - (self.vendedor_pct or 0.0))


class Sorteo(Base):
    __tablename__ = "sorteos"

    id = Column(Integer, primary_key=True, index=True)
    modulo = Column(Enum(ModuloJuego, name="modulo_juego"), nullable=False)
    horario = Column(String(20), nullable=False)
    fecha = Column(DateTime(timezone=True), nullable=False)
    estado = Column(Enum(EstadoSorteo, name="estado_sorteo"), default=EstadoSorteo.PROGRAMADO)
    resultados = Column(String(200), nullable=True)
    premio_fijo = Column(Float, nullable=True)         # solo rifa
    pozo_inicial = Column(Float, default=0.0)
    recaudado = Column(Float, default=0.0)
    pozo_extra = Column(Float, default=0.0)
    solo_participantes = Column(Boolean, default=False)
    participantes = Column(String(2000), nullable=True)
    busqueda_agotada = Column(Boolean, default=False)
    creado_en = Column(DateTime(timezone=True), server_default=func.now())

    # Reglas PROPIAS de este sorteo (si estan vacias se usan las reglas por defecto)
    precio_jugada = Column(Float, nullable=True)
    pozo_base = Column(Float, nullable=True)
    casa_pct = Column(Float, nullable=True)
    vendedor_pct = Column(Float, nullable=True)

    @property
    def pozo_actual(self):
        return (self.pozo_inicial or 0.0) + (self.pozo_extra or 0.0)

    @property
    def lista_resultados(self):
        if not self.resultados:
            return []
        return [int(x) for x in self.resultados.split(",") if x.strip() != ""]


class Jugada(Base):
    __tablename__ = "jugadas"

    id = Column(Integer, primary_key=True, index=True)
    sorteo_id = Column(Integer, ForeignKey("sorteos.id"), nullable=False)
    vendedor_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    revendedor_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    jugador_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    jugador_nombre = Column(String(100), nullable=True)
    numeros = Column(String(120), nullable=False)
    precio = Column(Float, nullable=False)
    estado = Column(Enum(EstadoJugada, name="estado_jugada"), default=EstadoJugada.PENDIENTE)
    premio = Column(Float, nullable=True)
    monto_casa = Column(Float, nullable=True)
    monto_vendedor = Column(Float, nullable=True)
    monto_revendedor = Column(Float, nullable=True)
    monto_pozo = Column(Float, nullable=True)
    creada_en = Column(DateTime(timezone=True), server_default=func.now())

    @property
    def lista_numeros(self):
        return [int(x) for x in self.numeros.split(",") if x.strip() != ""]
