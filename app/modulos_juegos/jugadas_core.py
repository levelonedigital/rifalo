from datetime import datetime

from app.core import auditoria
from app.modulos_juegos.modalidades import obtener
from app.modelos.juegos import EstadoSorteo, Jugada, Sorteo
from app.modelos.usuario import Usuario


def precio_de(sorteo: Sorteo) -> float:
    """Precio de la jugada: el del sorteo si esta configurado."""
    return sorteo.precio_jugada or 0.0


def momento_cierre(sorteo: Sorteo):
    """Fecha y hora limite para anotarse, o None si el sorteo no tiene cierre configurado."""
    if not sorteo.hora_cierre or ":" not in sorteo.hora_cierre:
        return None
    try:
        hora, minuto = (int(x) for x in sorteo.hora_cierre.split(":"))
    except ValueError:
        return None
    return sorteo.fecha.replace(hour=hora, minute=minuto, second=0, microsecond=0)


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
    vendedor_dueno: Usuario,
    revendedor_id=None,
    jugador_id=None,
    jugador_nombre=None,
) -> Jugada:
    """Valida y crea una jugada pendiente. Acepta sorteos programados o reprogramando,
    siempre que no haya pasado el horario de cierre para anotarse."""
    if sorteo.estado not in (EstadoSorteo.PROGRAMADO, EstadoSorteo.REPROGRAMANDO):
        raise ValueError("El sorteo no esta abierto para cargar jugadas")
    cierre = momento_cierre(sorteo)
    if cierre is not None:
        ahora = datetime.now(cierre.tzinfo) if cierre.tzinfo else datetime.now()
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
        vendedor_id=vendedor_dueno.id,
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
        usuario=vendedor_dueno,
    )
    sesion.commit()
    return jugada
