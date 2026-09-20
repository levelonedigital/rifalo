from sqlalchemy.orm import Session

from app.modelos.juegos import EstadoJugada, EstadoSorteo, Jugada, ReglasSistema, Sorteo
from app.modelos.usuario import Usuario
from app.modulos_juegos.modalidades import obtener


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
    """Aprueba y reparte el precio: casa, linea de venta y pozo (congelado incluido)."""
    sorteo = sesion.get(Sorteo, jugada.sorteo_id)
    modalidad = obtener(sorteo.modalidad)
    vendedor = sesion.get(Usuario, jugada.vendedor_id)
    revendedor = sesion.get(Usuario, jugada.revendedor_id) if jugada.revendedor_id else None

    casa_pct, linea_pct, pozo_pct = porcentajes_sorteo(sorteo, reglas)

    vend_efectivo = linea_pct
    if vendedor is not None and vendedor.comision_pct is not None:
        vend_efectivo = min(vendedor.comision_pct, linea_pct)
    rev_pct = 0.0
    if revendedor is not None:
        rev_pct = min(revendedor.comision_pct or 0.0, vend_efectivo)

    precio = jugada.precio
    base = base_pozo(sorteo)
    recaudado_previo = sorteo.recaudado or 0.0
    sorteo.recaudado = recaudado_previo + precio

    aporte_pozo = 0.0
    if modalidad and modalidad.requiere_pozo and recaudado_previo >= base:
        aporte_pozo = round(precio * pozo_pct / 100.0, 2)
    sorteo.pozo_extra = (sorteo.pozo_extra or 0.0) + aporte_pozo

    monto_rev = round(precio * rev_pct / 100.0, 2)
    monto_vend = round(precio * vend_efectivo / 100.0, 2) - monto_rev
    monto_casa = round(precio - monto_rev - monto_vend - aporte_pozo, 2)

    jugada.estado = EstadoJugada.APROBADA
    jugada.monto_casa = monto_casa
    jugada.monto_vendedor = monto_vend
    jugada.monto_revendedor = monto_rev
    jugada.monto_pozo = aporte_pozo
    return jugada


def liquidar_sorteo(sorteo: Sorteo, sesion: Session, reglas: ReglasSistema) -> dict:
    """Compara jugadas aprobadas contra resultados y asigna premios usando el plugin."""
    modalidad = obtener(sorteo.modalidad)
    if modalidad is None:
        return {"error": f"Modalidad {sorteo.modalidad} no encontrada"}

    resultados = sorteo.lista_resultados
    aprobadas = (
        sesion.query(Jugada)
        .filter(Jugada.sorteo_id == sorteo.id, Jugada.estado == EstadoJugada.APROBADA)
        .all()
    )
    ganadoras = []
    for j in aprobadas:
        numeros = j.lista_numeros
        if modalidad.gana(numeros, resultados):
            ganadoras.append(j)
        else:
            j.estado = EstadoJugada.PERDEDORA
            j.premio = 0.0

    pozo_pagado = 0.0
    if ganadoras:
        premio_unitario = modalidad.calcular_premio(ganadoras, sorteo.pozo_actual, sorteo.premio_fijo)
        for j in ganadoras:
            j.estado = EstadoJugada.GANADORA
            j.premio = premio_unitario
        pozo_pagado = round(premio_unitario * len(ganadoras), 2)
        if modalidad.requiere_pozo and not modalidad.usa_premio_fijo:
            sorteo.pozo_inicial = 0.0
            sorteo.pozo_extra = 0.0

    sorteo.estado = EstadoSorteo.LIQUIDADO
    return {
        "sorteo_id": sorteo.id,
        "modalidad": sorteo.modalidad,
        "horario": sorteo.horario,
        "jugadas_aprobadas": len(aprobadas),
        "ganadoras": [j.id for j in ganadoras],
        "pozo_pagado": round(pozo_pagado, 2),
        "pozo_sin_ganador": round(sorteo.pozo_actual, 2) if not ganadoras else 0.0,
    }


def nombres_participantes(sorteo_id: int, sesion: Session) -> str:
    jugadas = (
        sesion.query(Jugada)
        .filter(Jugada.sorteo_id == sorteo_id, Jugada.estado == EstadoJugada.APROBADA)
        .all()
    )
    nombres = set()
    for j in jugadas:
        nombres.add(j.jugador_nombre or f"jugada-{j.id}")
    return "|".join(sorted(nombres))


def crear_pozo_vacante(sesion: Session, origen: Sorteo, fecha, reglas: ReglasSistema) -> Sorteo:
    nuevo = Sorteo(
        modalidad=origen.modalidad,
        horario=origen.horario,
        fecha=fecha,
        pozo_inicial=origen.pozo_actual,
        solo_participantes=True,
        participantes=nombres_participantes(origen.id, sesion),
        precio_jugada=origen.precio_jugada,
        pozo_base=origen.pozo_base,
        casa_pct=origen.casa_pct,
        vendedor_pct=origen.vendedor_pct,
    )
    sesion.add(nuevo)
    return nuevo
