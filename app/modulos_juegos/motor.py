from sqlalchemy.orm import Session

from app.modelos.juegos import CupoVendedor, EstadoJugada, EstadoSorteo, Jugada, ReglasSistema, Sorteo
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
    "info_premio_compartido",
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
    return sorteo.pozo_base or 0.0


def porcentajes_sorteo(sorteo: Sorteo, reglas: ReglasSistema):
    casa = sorteo.casa_pct if sorteo.casa_pct is not None else 30.0
    linea = sorteo.vendedor_pct if sorteo.vendedor_pct is not None else reglas.vendedor_pct
    pozo = max(0.0, 100.0 - casa - linea)
    return casa, linea, pozo


def aprobar_jugada(sesion: Session, jugada: Jugada, reglas: ReglasSistema) -> Jugada:
    sorteo = sesion.get(Sorteo, jugada.sorteo_id)
    if sorteo is None:
        raise ValueError("Sorteo no encontrado para la jugada")
    fn = descubrimiento.obtener_aprobar(sorteo.modalidad)
    if fn is None:
        raise ValueError(f"La modalidad {sorteo.modalidad} no esta disponible para aprobar jugadas")
    return fn(sesion, jugada, reglas)


def liquidar_sorteo(sorteo: Sorteo, sesion: Session, reglas: ReglasSistema) -> dict:
    fn = descubrimiento.obtener_liquidar(sorteo.modalidad)
    if fn is None:
        return {"error": f"Modalidad {sorteo.modalidad} no encontrada o sin modulo de liquidacion"}
    return fn(sorteo, sesion, reglas)


ESTADOS_VENDIDAS = [EstadoJugada.APROBADA, EstadoJugada.GANADORA, EstadoJugada.PERDEDORA]


def nombres_participantes(sorteo_id: int, sesion: Session) -> str:
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


# ---------- COMPAT: validacion de numeros unicos de rifa ----------

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


# ---------- AVISO: jugadas iguales y premio estimado (clasico / semanal) ----------

def info_premio_compartido(sesion: Session, sorteo: Sorteo, clave_numeros: str, incluir_pendiente: bool = False) -> dict:
    """Para modalidades de pozo repartido (clasico/semanal): cuenta cuantas OTRAS jugadas
    vendidas tienen la misma combinacion y estima el premio si esta combinacion ganara,
    con el pozo al momento. En rifa (premio fijo) no aplica: devuelve aplica=False.

    incluir_pendiente=True: la jugada propia todavia es PENDIENTE (no sumo al pozo),
      entonces sumo su aporte estimado al pozo y la cuento como un ganador mas.
    incluir_pendiente=False: la jugada propia ya esta VENDIDA (ya sumo al pozo),
      entonces el pozo actual ya la incluye y los ganadores son todas las vendidas iguales.
    """
    from app.modulos_juegos.modalidades import obtener as obtener_modalidad
    modalidad = obtener_modalidad(sorteo.modalidad)
    if modalidad is None or getattr(modalidad, "usa_premio_fijo", False):
        return {"aplica": False, "coincidencias": 0, "premio_estimado": None, "pozo_estimado": None}

    vendidas_iguales = (
        sesion.query(Jugada)
        .filter(
            Jugada.sorteo_id == sorteo.id,
            Jugada.numeros == clave_numeros,
            Jugada.estado.in_(ESTADOS_VENDIDAS),
        )
        .count()
    )
    reglas = obtener_reglas(sesion)
    _, _, pozo_pct = porcentajes_sorteo(sorteo, reglas)
    aporte_pozo = round((sorteo.precio_jugada or 0.0) * pozo_pct / 100.0, 2)

    if incluir_pendiente:
        pozo_estimado = round((sorteo.pozo_actual or 0.0) + aporte_pozo, 2)
        ganadores = vendidas_iguales + 1
        coincidencias_otras = vendidas_iguales
    else:
        pozo_estimado = round(sorteo.pozo_actual or 0.0, 2)
        ganadores = max(vendidas_iguales, 1)
        coincidencias_otras = max(vendidas_iguales - 1, 0)

    premio_estimado = round(pozo_estimado / ganadores, 2) if ganadores > 0 else None
    return {
        "aplica": True,
        "coincidencias": coincidencias_otras,
        "premio_estimado": premio_estimado,
        "pozo_estimado": pozo_estimado,
    }

# ---------- CUPOS DE VENTA POR VENDEDOR Y SORTEO ----------

def cupo_vendedor_disponible(sesion: Session, sorteo: Sorteo, vendedor: Usuario):
    """Devuelve (tiene_registro, disponibles).

    Si el admin aun no asigno cupos para este sorteo+vendedor, no hay registro y se
    devuelve (False, None) = sin limite (compatibilidad).
    """
    reg = (
        sesion.query(CupoVendedor)
        .filter(CupoVendedor.sorteo_id == sorteo.id, CupoVendedor.vendedor_id == vendedor.id)
        .first()
    )
    if reg is None:
        return False, None
    return True, max((reg.cupo_total or 0) - (reg.cupo_usado or 0), 0)


def consumir_cupo_vendedor(sesion: Session, sorteo: Sorteo, vendedor: Usuario) -> bool:
    """Descuenta 1 cupo de venta del vendedor para el sorteo.

    True si pudo descontar (o si no hay registro = sin limite). False si el vendedor
    ya no tiene cupos para este sorteo.
    """
    reg = (
        sesion.query(CupoVendedor)
        .filter(CupoVendedor.sorteo_id == sorteo.id, CupoVendedor.vendedor_id == vendedor.id)
        .first()
    )
    if reg is None:
        return True
    if (reg.cupo_usado or 0) >= (reg.cupo_total or 0):
        return False
    reg.cupo_usado = (reg.cupo_usado or 0) + 1
    sesion.commit()
    return True

# ---------- CUPOS DE VENTA POR REVENDEDOR Y SORTEO ----------

def cupo_revendedor_disponible(sesion: Session, sorteo: Sorteo, rev: Usuario):
    """Devuelve (tiene_registro, disponibles) del cupo propio del revendedor.

    Si el vendedor aun no le asigno cupos, no hay registro y se devuelve (False, None)
    = sin limite propio (descuenta del cupo del vendedor, compatibilidad).
    """
    from app.modelos.juegos import CupoRevendedor
    reg = (
        sesion.query(CupoRevendedor)
        .filter(CupoRevendedor.sorteo_id == sorteo.id, CupoRevendedor.revendedor_id == rev.id)
        .first()
    )
    if reg is None:
        return False, None
    return True, max((reg.cupo_total or 0) - (reg.cupo_usado or 0), 0)

def consumir_cupo_revendedor(sesion: Session, sorteo: Sorteo, rev: Usuario) -> bool:
    """Descuenta 1 cupo del revendedor. True si pudo (o si no hay registro). False si sin cupo."""
    from app.modelos.juegos import CupoRevendedor
    reg = (
        sesion.query(CupoRevendedor)
        .filter(CupoRevendedor.sorteo_id == sorteo.id, CupoRevendedor.revendedor_id == rev.id)
        .first()
    )
    if reg is None:
        return True
    if (reg.cupo_usado or 0) >= (reg.cupo_total or 0):
        return False
    reg.cupo_usado = (reg.cupo_usado or 0) + 1
    sesion.commit()
    return True
