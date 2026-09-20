import enum
from sqlalchemy import Column, Integer, String, Boolean, Float, DateTime, Enum, ForeignKey
from sqlalchemy.sql import func

from app.core.database import Base


class EstadoSorteo(str, enum.Enum):
    PROGRAMADO = "programado"
    CERRADO = "cerrado"
    LIQUIDADO = "liquidado"
    REPROGRAMANDO = "reprogramando"   # hora cancelada, jugadas y pozo siguen en juego


class EstadoJugada(str, enum.Enum):
    PENDIENTE = "pendiente"
    APROBADA = "aprobada"
    RECHAZADA = "rechazada"
    GANADORA = "ganadora"
    PERDEDORA = "perdedora"
    CANCELADA = "cancelada"


class ReglasSistema(Base):
    """Configuracion de sistema (horarios, busqueda, ventana semanal). Una fila, id=1."""
    __tablename__ = "reglas_sistema"

    id = Column(Integer, primary_key=True, default=1)
    horarios = Column(String(300), default='{"matutina":"11:30","vespertina":"14:30","siesta":"17:30","tarde":"19:30","nocturna":"22:00"}')
    semanal_horario = Column(String(20), default="nocturna")
    semanal_dia_inicio = Column(Integer, default=0)   # 0=lunes
    semanal_dia_fin = Column(Integer, default=4)      # 4=viernes
    busqueda_inicio_min = Column(Integer, default=1)
    busqueda_intervalo_min = Column(Integer, default=2)
    busqueda_duracion_min = Column(Integer, default=16)
    vendedor_pct = Column(Float, default=20.0)        # comision por defecto de vendedores sin % propio

    def dict_horarios(self):
        import json
        try:
            return json.loads(self.horarios or "{}")
        except Exception:
            return {}


class PlantillaSorteo(Base):
    """Guia guardada por el admin: una configuracion de sorteo con nombre."""
    __tablename__ = "plantillas_sorteo"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), nullable=False)
    modalidad = Column(String(30), nullable=False)
    horario = Column(String(20), nullable=True)
    precio_jugada = Column(Float, nullable=False)
    pozo_base = Column(Float, nullable=True)
    casa_pct = Column(Float, nullable=False)
    vendedor_pct = Column(Float, nullable=True)
    premio_fijo = Column(Float, nullable=True)
    descripcion = Column(String(300), nullable=True)


class Sorteo(Base):
    __tablename__ = "sorteos"

    id = Column(Integer, primary_key=True, index=True)
    modalidad = Column(String(30), nullable=False)   # clave de la modalidad (plugin)
    horario = Column(String(20), nullable=False)
    fecha = Column(DateTime(timezone=True), nullable=False)
    estado = Column(Enum(EstadoSorteo, name="estado_sorteo"), default=EstadoSorteo.PROGRAMADO)
    resultados = Column(String(200), nullable=True)  # 20 numeros oficiales separados por coma
    premio_fijo = Column(Float, nullable=True)
    pozo_inicial = Column(Float, default=0.0)
    recaudado = Column(Float, default=0.0)
    pozo_extra = Column(Float, default=0.0)
    solo_participantes = Column(Boolean, default=False)
    participantes = Column(String(2000), nullable=True)
    busqueda_agotada = Column(Boolean, default=False)
    creado_en = Column(DateTime(timezone=True), server_default=func.now())

    # Configuracion propia de este sorteo
    precio_jugada = Column(Float, nullable=True)
    pozo_base = Column(Float, nullable=True)
    casa_pct = Column(Float, nullable=True)
    vendedor_pct = Column(Float, nullable=True)
    minimo_cubrir = Column(Float, nullable=True)       # rifa: costo minimo a cubrir (vacio = premio fijo)
    aviso_costo_enviado = Column(Boolean, default=False)  # ya se aviso al admin a 30 min del sorteo

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


class Aviso(Base):
    """Cartel visible en el panel: cancelaciones, reprogramaciones y alertas al admin."""
    __tablename__ = "avisos"

    id = Column(Integer, primary_key=True, index=True)
    texto = Column(String(500), nullable=False)
    destino = Column(String(20), default="todos")   # todos | admin
    creado_en = Column(DateTime(timezone=True), server_default=func.now())
