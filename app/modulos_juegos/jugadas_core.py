from datetime import datetime, timedelta, timezone

from app.core import auditoria
from app.core.config import Configuracion
from app.modulos_juegos.modalidades import obtener
from app.modelos.juegos import EstadoSorteo, Jugada, Sorteo
from app.modelos.usuario import Usuario


def _zona():
    """Zona horaria oficial del sistema (Argentina). Con respaldo a UTC-3 fijo."""
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(Configuracion.ZONA_HORARIA)
    except Exception:
        return timezone(timedelta(hours=-3))


def precio_de(sorteo: Sorteo) -> float:
    return sorteo.precio_jugada or 0.0


def momento_cierre(sorteo: Sorteo):
    if not sorteo.hora_cierre or ":" not in sorteo.hora_cierre:
        return None
    try:
        hora, minuto = (int(x) for x in sorteo.hora_cierre.split(":"))
    except ValueError:
        return None
    f = sorteo.fecha
    return datetime(f.year, f.month, f.day, hora, minuto, 0, tzinfo=_zona())


def validar_numeros(sorteo: Sorteo, numeros) -> str | None:
    modalidad = obtener(sorteo.modalidad)
    if modalidad is None:
        return f"Modalidad {sorteo.modalidad} no existe"
    if len(numeros) != modalidad.cantidad_numeros:
        return f"La modalidad {modalidad.nombre} requiere {modalidad.cantidad_numeros} numeros"
    for n in numeros:
        if not isinstance(n, int) or n < 0 or n > 99:
            return "Los numeros deben estar entre 0 y 99"
    if not modalidad.permite_repetidos and len(set(numeros)) != len(numeros):
        return "En una misma jugada no puede repetirse un numero"
    return None


def crear_jugada(
    sesion,
    sorteo: Sorteo,
    numeros,
    vendedor: Usuario,
    revendedor_id=None,
    jugador_id=None,
    jugador_nombre=None,
) -> Jugada:
    if sorteo.estado not in (EstadoSorteo.PROGRAMADO, EstadoSorteo.REPROGRAMANDO):
        raise ValueError("El sorteo no esta abierto para cargar jugadas")
    cierre = momento_cierre(sorteo)
    if cierre is not None:
        ahora = datetime.now(_zona())
        if ahora > cierre:
            raise ValueError("El horario de cierre para anotarse ya paso en este sorteo")
    error = validar_numeros(sorteo, numeros)
    if error:
        raise ValueError(error)
    if sorteo.solo_participantes:
        habilitados = {p.strip().lower() for p in (sorteo.participantes or "").split("|") if p.strip()}
        nombre = (jugador_nombre or "").strip().lower()
        if nombre not in habilitados:
            raise ValueError("Sorteo de pozo vacante: solo pueden jugar quienes participaron del original")
    jugada = Jugada(
        sorteo_id=sorteo.id,
        vendedor_id=vendedor.id,
        revendedor_id=revendedor_id,
        jugador_id=jugador_id,
        jugador_nombre=jugador_nombre,
        numeros=",".join(f"{n:02d}" for n in numeros),
        precio=precio_de(sorteo),
    )
    sesion.add(jugada)
    sesion.commit()
    sesion.refresh(jugada)
    auditoria.registrar(
        sesion,
        "JUGADA_CARGADA",
        detalle=f"sorteo={sorteo.id} numeros={jugada.numeros} precio={jugada.precio}",
        usuario=vendedor,
    )
    sesion.commit()
    return jugada


def crear_cupo(
    sesion,
    sorteo: Sorteo,
    vendedor: Usuario,
    revendedor_id=None,
    jugador_id=None,
    jugador_nombre=None,
) -> Jugada:
    """Crea un CUPO: una jugada APROBADA sin numeros (numeros='').

    El vendedor/revendedor la 'vende' cobrando fuera del sistema. Al aprobarse en el
    momento, el precio se reparte y suma al pozo inmediatamente. El jugador despues
    completa los numeros de este cupo para participar. Si no lo usa, queda como jugada
    vendida sin numeros (no gana) y el dinero queda repartido.
    """
    if sorteo.estado not in (EstadoSorteo.PROGRAMADO, EstadoSorteo.REPROGRAMANDO):
        raise ValueError("El sorteo no esta abierto para vender jugadas")
    cierre = momento_cierre(sorteo)
    if cierre is not None:
        ahora = datetime.now(_zona())
        if ahora > cierre:
            raise ValueError("El horario de cierre para anotarse ya paso en este sorteo")
    if sorteo.solo_participantes:
        habilitados = {p.strip().lower() for p in (sorteo.participantes or "").split("|") if p.strip()}
        nombre = (jugador_nombre or "").strip().lower()
        if nombre not in habilitados:
            raise ValueError("Sorteo de pozo vacante: solo pueden jugar quienes participaron del original")
    jugada = Jugada(
        sorteo_id=sorteo.id,
        vendedor_id=vendedor.id,
        revendedor_id=revendedor_id,
        jugador_id=jugador_id,
        jugador_nombre=jugador_nombre,
        numeros="",
        precio=precio_de(sorteo),
    )
    sesion.add(jugada)
    sesion.commit()
    sesion.refresh(jugada)
    auditoria.registrar(
        sesion,
        "CUPO_CREADO",
        detalle=f"sorteo={sorteo.id} jugador={jugador_nombre} precio={jugada.precio}",
        usuario=vendedor,
    )
    sesion.commit()
    return jugada
