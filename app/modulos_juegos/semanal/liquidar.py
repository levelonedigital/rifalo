"""Liquidacion de SEMANAL, independiente del motor general.

Compara los 10 numeros contra los acumulados y reparte el pozo entre los ganadores.
"""

from app.modelos.juegos import EstadoJugada, EstadoSorteo, Jugada


def liquidar_sorteo_semanal(sorteo, sesion, reglas) -> dict:
    resultados = sorteo.lista_resultados
    aprobadas = (
        sesion.query(Jugada)
        .filter(Jugada.sorteo_id == sorteo.id, Jugada.estado == EstadoJugada.APROBADA)
        .all()
    )

    ganadoras = []
    for j in aprobadas:
        if resultados and set(j.lista_numeros).issubset(resultados):
            ganadoras.append(j)
        else:
            j.estado = EstadoJugada.PERDEDORA
            j.premio = 0.0

    pozo_pagado = 0.0
    if ganadoras:
        premio_unitario = round(sorteo.pozo_actual / len(ganadoras), 2)
        for j in ganadoras:
            j.estado = EstadoJugada.GANADORA
            j.premio = premio_unitario
        pozo_pagado = round(premio_unitario * len(ganadoras), 2)
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
