from sqlalchemy.orm import Session

from app.modelos.juegos import (
    EstadoJugada,
    EstadoSorteo,
    Jugada,
    ModuloJuego,
    ReglasSistema,
    Sorteo,
)
from app.modelos.usuario import Usuario


def obtener_reglas(sesion: Session) -> ReglasSistema:
    """Devuelve la fila unica de reglas, creandola si no existe."""
    reglas = sesion.get(ReglasSistema, 1)
    if reglas is None:
        reglas = ReglasSistema(id=1)
        sesion.add(reglas)
        sesion.commit()
        sesion.refresh(reglas)
    return reglas


def base_pozo(sorteo: Sorteo, reglas: ReglasSistema) -> float:
    if sorteo.modulo == ModuloJuego.CLASICO:
        return reglas.pozo_base_clasico or 0.0
    if sorteo.modulo == ModuloJuego.SEMANAL:
        return reglas.pozo_base_semanal or 0.0
    return 0.0


def aprobar_jugada(sesion: Session, jugada: Jugada, reglas: ReglasSistema) -> Jugada:
    """Aprueba la jugada y reparte su precio: casa, vendedor, revendedor y pozo.

    Regla del pozo congelado: mientras lo recaudado del sorteo no iguale la
    base configurada, el % de pozo queda para la casa. Recien a partir de ahi
    el pozo empieza a crecer.
    No hace commit.
    """
    sorteo = sesion.get(Sorteo, jugada.sorteo_id)
    vendedor = sesion.get(Usuario, jugada.vendedor_id)
    revendedor = sesion.get(Usuario, jugada.revendedor_id) if jugada.revendedor_id else None

    v_pct = vendedor.comision_pct if vendedor and vendedor.comision_pct is not None else reglas.vendedor_pct
    r_pct = 0.0
    if revendedor is not None:
        r_pct = min(revendedor.comision_pct or 0.0, v_pct)

    precio = jugada.precio
    base = base_pozo(sorteo, reglas)
    recaudado_previo = sorteo.recaudado or 0.0
    sorteo.recaudado = recaudado_previo + precio

    aporte_pozo = 0.0
    if sorteo.modulo != ModuloJuego.RIFA and recaudado_previo >= base:
        aporte_pozo = round(precio * (reglas.pozo_pct or 0.0) / 100.0, 2)
    sorteo.pozo_extra = (sorteo.pozo_extra or 0.0) + aporte_pozo

    monto_rev = round(precio * r_pct / 100.0, 2)
    monto_vend = round(precio * v_pct / 100.0, 2) - monto_rev
    monto_casa = round(precio - monto_rev - monto_vend - aporte_pozo, 2)

    jugada.estado = EstadoJugada.APROBADA
    jugada.monto_casa = monto_casa
    jugada.monto_vendedor = monto_vend
    jugada.monto_revendedor = monto_rev
    jugada.monto_pozo = aporte_pozo
    return jugada


def liquidar_sorteo(sorteo: Sorteo, sesion: Session, reglas: ReglasSistema) -> dict:
    """Compara las jugadas aprobadas contra los resultados y asigna premios.

    Clasico y semanal: gana si TODOS sus numeros estan entre los resultados.
    Rifa: gana si su numero coincide con el 1er premio.
    No hace commit.
    """
    resultados = set(sorteo.lista_resultados)
    primer_premio = sorteo.lista_resultados[0] if sorteo.lista_resultados else None
    aprobadas = (
        sesion.query(Jugada)
        .filter(Jugada.sorteo_id == sorteo.id, Jugada.estado == EstadoJugada.APROBADA)
        .all()
    )
    ganadoras = []
    for j in aprobadas:
        numeros = j.lista_numeros
        if sorteo.modulo == ModuloJuego.RIFA:
            gana = primer_premio is not None and numeros and numeros[0] == primer_premio
        else:
            gana = bool(resultados) and set(numeros).issubset(resultados)
        if gana:
            ganadoras.append(j)
        else:
            j.estado = EstadoJugada.PERDEDORA
            j.premio = 0.0

    pozo_pagado = 0.0
    if ganadoras:
        if sorteo.modulo == ModuloJuego.RIFA:
            for j in ganadoras:
                j.estado = EstadoJugada.GANADORA
                j.premio = sorteo.premio_fijo or 0.0
                pozo_pagado += j.premio
        else:
            parte = round(sorteo.pozo_actual / len(ganadoras), 2)
            for j in ganadoras:
                j.estado = EstadoJugada.GANADORA
                j.premio = parte
            pozo_pagado = round(parte * len(ganadoras), 2)
            sorteo.pozo_inicial = 0.0
            sorteo.pozo_extra = 0.0

    sorteo.estado = EstadoSorteo.LIQUIDADO
    return {
        "sorteo_id": sorteo.id,
        "modulo": sorteo.modulo.value,
        "horario": sorteo.horario,
        "jugadas_aprobadas": len(aprobadas),
        "ganadoras": [j.id for j in ganadoras],
        "pozo_pagado": round(pozo_pagado, 2),
        "pozo_sin_ganador": round(sorteo.pozo_actual, 2) if not ganadoras else 0.0,
    }


def nombres_participantes(sorteo_id: int, sesion: Session) -> str:
    """Lista de nombres habilitados para un pozo vacante."""
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
    """Sorteo especial con el pozo sin ganador, solo para participantes del original."""
    nuevo = Sorteo(
        modulo=origen.modulo,
        horario=origen.horario,
        fecha=fecha,
        pozo_inicial=origen.pozo_actual,
        solo_participantes=True,
        participantes=nombres_participantes(origen.id, sesion),
    )
    sesion.add(nuevo)
    return nuevo
