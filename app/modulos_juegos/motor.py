from sqlalchemy.orm import Session

from app.modelos.juegos import EstadoJugada, EstadoSorteo, Jugada, ReglasSistema, Sorteo
from app.modelos.usuario import Usuario
from app.modulos_juegos import descubrimiento

__all__ = [
    "obtener_reglas",
    "base_pozo",
    "porcentajes_sorteo",
    "aprobar_jugada",
    "liquidar_sorteo",
    "nombres_participantes",
    "crear_pozo_vacante",
    "es_rifa_numero_unico",
    "numeros_ocupados_rifa",
    "validar_numeros_rifa",
]


def obtener_reglas(sesion: Session) -> ReglasSistema:
    reglas = sesion.get(ReglasSistema, 1)
    if reglas is None:
        reglas = ReglasSistema(id=1)
        sesion.add(reglas)
        sesion.commit()
        sesion.refresh(reglas)
    return reglas


def base_pozo(sorteo: Sorteo) -> float:
    """Pozo base del sorteo (override o 0 si no hay)."""
    return sorteo.pozo_base or 0.0


def porcentajes_sorteo(sorteo: Sorteo, reglas: ReglasSistema):
    """Devuelve (casa_pct, vendedor_linea_pct, pozo_pct) efectivos de este sorteo."""
    casa = sorteo.casa_pct if sorteo.casa_pct is not None else 30.0
    linea = sorteo.vendedor_pct if sorteo.vendedor_pct is not None else reglas.vendedor_pct
    pozo = max(0.0, 100.0 - casa - linea)
    return casa, linea, pozo


def aprobar_jugada(sesion: Session, jugada: Jugada, reglas: ReglasSistema) -> Jugada:
    """Aprueba y reparte el precio delegando en el modulo aprobar de la modalidad.

    El motor no sabe que modalidad es: pregunta al descubrimiento. Si la modalidad no
    esta registrada o no trae aprobar.py, se rechaza (no se aprueba a ciegas).
    """
    sorteo = sesion.get(Sorteo, jugada.sorteo_id)
    if sorteo is None:
        raise ValueError("Sorteo no encontrado para la jugada")
    fn = descubrimiento.obtener_aprobar(sorteo.modalidad)
    if fn is None:
        raise ValueError(f"La modalidad {sorteo.modalidad} no esta disponible para aprobar jugadas")
    return fn(sesion, jugada, reglas)


def liquidar_sorteo(sorteo: Sorteo, sesion: Session, reglas: ReglasSistema) -> dict:
    """Licuida delegando en el modulo liquidar de la modalidad descubierta."""
    fn = descubrimiento.obtener_liquidar(sorteo.modalidad)
    if fn is None:
        return {"error": f"Modalidad {sorteo.modalidad} no encontrada o sin modulo de liquidacion"}
    return fn(sorteo, sesion, reglas)


ESTADOS_VENDIDAS = [EstadoJugada.APROBADA, EstadoJugada.GANADORA, EstadoJugada.PERDEDORA]


def nombres_participantes(sorteo_id: int, sesion: Session) -> str:
    """Nombres de quienes jugaron el sorteo (jugadas vendidas), para el pozo vacante."""
    jugadas = (
        sesion.query(Jugada)
        .filter(Jugada.sorteo_id == sorteo_id, Jugada.estado.in_(ESTADOS_VENDIDAS))
        .all()
    )
    nombres = set()
    for j in jugadas:
        nombres.add(j.jugador_nombre or f"jugada-{j.id}")
    return "|".join(sorted(nombres))


def crear_pozo_vacante(sesion: Session, origen: Sorteo, fecha, reglas: ReglasSistema) -> Sorteo:
    """Crea el sorteo vacante: arranca con el pozo retenido del origen, SIN pozo base."""
    hora = reglas.dict_horarios().get(origen.horario, "")
    titulo = f"Pozo vacante sorteo del {fecha.strftime('%d/%m/%Y')} a {hora}"
    nuevo = Sorteo(
        modalidad=origen.modalidad,
        horario=origen.horario,
        fecha=fecha,
        pozo_inicial=origen.pozo_actual,
        pozo_base=0.0,
        solo_participantes=True,
        participantes=nombres_participantes(origen.id, sesion),
        precio_jugada=origen.precio_jugada,
        casa_pct=origen.casa_pct,
        vendedor_pct=origen.vendedor_pct,
        titulo=titulo,
    )
    sesion.add(nuevo)
    return nuevo


# ---------- COMPAT: validacion de numeros unicos de rifa (resuelta dinamicamente) ----------
# Los routers de rol llaman a estas funciones por nombre; se resuelven contra el modulo
# validar de la modalidad rifa sin que el motor la importe estaticamente.

def _modulo_validar_rifa():
    return descubrimiento.obtener_modulo("rifa", "validar")


def es_rifa_numero_unico(sorteo: Sorteo) -> bool:
    m = _modulo_validar_rifa()
    if m is None:
        return False
    return m.es_rifa_numero_unico(sorteo)


def numeros_ocupados_rifa(sesion: Session, sorteo: Sorteo):
    m = _modulo_validar_rifa()
    if m is None:
        return None
    return m.numeros_ocupados_rifa(sesion, sorteo)


def validar_numeros_rifa(sesion: Session, sorteo: Sorteo, numeros) -> None:
    m = _modulo_validar_rifa()
    if m is None:
        return
    return m.validar_numeros_rifa(sesion, sorteo, numeros)
