import enum
from sqlalchemy import Column, Integer, String, Boolean, Float, DateTime, Date, Enum, ForeignKey, Text
from sqlalchemy.sql import func

from app.core.database import Base


class EstadoSorteo(str, enum.Enum):
    PREPARACION = "preparacion"
    PROGRAMADO = "programado"
    CERRADO = "cerrado"
    LIQUIDADO = "liquidado"
    REPROGRAMANDO = "reprogramando"


class EstadoJugada(str, enum.Enum):
    PENDIENTE = "pendiente"
    APROBADA = "aprobada"
    RECHAZADA = "rechazada"
    GANADORA = "ganadora"
    PERDEDORA = "perdedora"
    CANCELADA = "cancelada"


class ReglasSistema(Base):
    __tablename__ = "reglas_sistema"

    id = Column(Integer, primary_key=True, default=1)
    horarios = Column(String(300), default='{"matutina":"11:30","vespertina":"14:30","siesta":"17:30","tarde":"19:30","nocturna":"22:00"}')
    semanal_horario = Column(String(20), default="nocturna")
    semanal_dia_inicio = Column(Integer, default=0)
    semanal_dia_fin = Column(Integer, default=4)
    busqueda_inicio_min = Column(Integer, default=1)
    busqueda_intervalo_min = Column(Integer, default=2)
    busqueda_duracion_min = Column(Integer, default=16)
    vendedor_pct = Column(Float, default=20.0)

    def dict_horarios(self):
        import json
        try:
            return json.loads(self.horarios or "{}")
        except Exception:
            return {}


class PlantillaSorteo(Base):
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
    modalidad = Column(String(30), nullable=False)
    horario = Column(String(20), nullable=False)
    fecha = Column(DateTime(timezone=True), nullable=False)
    hora_cierre = Column(String(5), nullable=True)
    estado = Column(Enum(EstadoSorteo, name="estado_sorteo"), default=EstadoSorteo.PREPARACION)
    resultados = Column(String(200), nullable=True)
    premio_fijo = Column(Float, nullable=True)
    pozo_inicial = Column(Float, default=0.0)
    recaudado = Column(Float, default=0.0)
    pozo_extra = Column(Float, default=0.0)
    pozo_cubierto = Column(Float, default=0.0)
    solo_participantes = Column(Boolean, default=False)
    participantes = Column(String(2000), nullable=True)
    busqueda_agotada = Column(Boolean, default=False)
    creado_en = Column(DateTime(timezone=True), server_default=func.now())
    # Imagen de presentacion: URL externa (legacy) o data URI base64 subida por el admin.
    imagen_url = Column(String(500), nullable=True)
    imagen_data = Column(Text, nullable=True)
    detalle = Column(String(1000), nullable=True)
    titulo = Column(String(120), nullable=True)
    # Nombre del premio: lo que ve el jugador en vez del monto. Ej: "Smart TV 55 pulgadas".
    premio_nombre = Column(String(200), nullable=True)

    precio_jugada = Column(Float, nullable=True)
    pozo_base = Column(Float, nullable=True)
    casa_pct = Column(Float, nullable=True)
    vendedor_pct = Column(Float, nullable=True)
    minimo_cubrir = Column(Float, nullable=True)
    aviso_costo_enviado = Column(Boolean, default=False)

    # Configuracion POR SORTEO de la busqueda automatica (None = usa el default del sistema).
    busqueda_inicio_min = Column(Integer, nullable=True)
    busqueda_intervalo_min = Column(Integer, nullable=True)
    busqueda_duracion_min = Column(Integer, nullable=True)
    # Configuracion POR SORTEO del semanal (None = usa el default del sistema).
    semanal_dia_inicio = Column(Integer, nullable=True)
    semanal_dia_fin = Column(Integer, nullable=True)

    @property
    def imagen_visible(self):
        """Data URI si el admin subio archivo; si no, la URL externa; si no, None."""
        return self.imagen_data or self.imagen_url or None

    @property
    def pozo_actual(self):
        return (self.pozo_inicial or 0.0) + (self.pozo_extra or 0.0)

    @property
    def pozo_cubierto_total(self):
        return (self.pozo_cubierto or 0.0) + (self.pozo_extra or 0.0)

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
    monto_cubrir = Column(Float, nullable=True)
    premio_pagado = Column(Boolean, default=False)
    comision_pagada = Column(Boolean, default=False)
    premio_cobrado = Column(Boolean, default=False)
    creada_en = Column(DateTime(timezone=True), server_default=func.now())

    @property
    def lista_numeros(self):
        return [int(x) for x in self.numeros.split(",") if x.strip() != ""]


class LiquidacionVendedor(Base):
    """Liquidacion de comisiones de un vendedor en un rango de fechas (gestion del admin)."""
    __tablename__ = "liquidaciones_vendedor"

    id = Column(Integer, primary_key=True, index=True)
    vendedor_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    desde = Column(Date, nullable=False)
    hasta = Column(Date, nullable=False)
    monto = Column(Float, nullable=False, default=0.0)
    detalle = Column(String(4000), nullable=True)
    pagado_admin = Column(Boolean, default=False)
    cobrado_vendedor = Column(Boolean, default=False)
    pagado_en = Column(DateTime(timezone=True), nullable=True)
    cobrado_en = Column(DateTime(timezone=True), nullable=True)
    creada_en = Column(DateTime(timezone=True), server_default=func.now())


class Aviso(Base):
    __tablename__ = "avisos"

    id = Column(Integer, primary_key=True, index=True)
    texto = Column(String(500), nullable=False)
    destino = Column(String(20), default="todos")
    creado_en = Column(DateTime(timezone=True), server_default=func.now())

class CupoVendedor(Base):
    """Cupo de jugadas que el admin habilita a un vendedor para un sorteo.

    Se descuenta con cada venta del vendedor (cupos a jugadores, venta directa) y con
    lo que vendan sus revendedores. Si no hay registro para un sorteo+vendedor, el
    vendedor no tiene limite (compatibilidad hasta que el admin asigne cupos).
    """
    __tablename__ = "cupos_vendedor"

    id = Column(Integer, primary_key=True, index=True)
    sorteo_id = Column(Integer, ForeignKey("sorteos.id"), nullable=False)
    vendedor_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    cupo_total = Column(Integer, default=0)
    cupo_usado = Column(Integer, default=0)

class PagoVendedor(Base):
    """Registro de pago del vendedor al administrador por jugadas vendidas de un sorteo.

    El admin confirma que el vendedor le pago X jugadas de ese sorteo. Queda como
    historial de rendicion (pagos parciales por sorteo).
    """
    __tablename__ = "pagos_vendedor"

    id = Column(Integer, primary_key=True, index=True)
    sorteo_id = Column(Integer, ForeignKey("sorteos.id"), nullable=False)
    vendedor_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    cantidad_jugadas = Column(Integer, nullable=False)
    monto = Column(Float, nullable=False)
    creado_en = Column(DateTime(timezone=True), server_default=func.now())

class CupoRevendedor(Base):
    """Cupo de jugadas que el VENDEDOR le cede a un revendedor para un sorteo.

    Se descuenta del cupo del vendedor al asignarlo. El revendedor consume de aca al
    vender. Si no hay registro, el revendedor vende sin limite propio (descuntando del
    cupo del vendedor, compatibilidad).
    """
    __tablename__ = "cupos_revendedor"

    id = Column(Integer, primary_key=True, index=True)
    sorteo_id = Column(Integer, ForeignKey("sorteos.id"), nullable=False)
    vendedor_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    revendedor_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    cupo_total = Column(Integer, default=0)
    cupo_usado = Column(Integer, default=0)

class PagoRevendedor(Base):
    """Registro de pago del revendedor al vendedor por jugadas vendidas de un sorteo."""
    __tablename__ = "pagos_revendedor"

    id = Column(Integer, primary_key=True, index=True)
    sorteo_id = Column(Integer, ForeignKey("sorteos.id"), nullable=False)
    vendedor_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    revendedor_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    cantidad_jugadas = Column(Integer, nullable=False)
    monto = Column(Float, nullable=False)
    creado_en = Column(DateTime(timezone=True), server_default=func.now())
