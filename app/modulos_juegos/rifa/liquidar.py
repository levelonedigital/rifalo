"""Liquidacion de RIFA, independiente del motor general.

Compara el numero de cada jugada contra el 1er premio. Las ganadoras cobran el
premio fijo. El excedente del acumulado (lo que sobro de la meta) NO se limpia:
queda como ganancia de la casa.
"""

from app.modelos.juegos import EstadoJugada, EstadoSorteo, Jugada


def liquidar_sorteo_rifa(sorteo, sesion, reglas) -> dict:
    resultados = sorteo.lista_resultados
    aprobadas = (
        sesion.query(Jugada)
        .filter(Jugada.sorteo_id == sorteo.id, Jugada.estado == EstadoJugada.APROBADA)
        .all()
    )

    ganadoras = []
    for j in aprobadas:
        numeros = j.lista_numeros
        if numeros and resultados and numeros[0] == resultados[0]:
            ganadoras.append(j)
        else:
            j.estado = EstadoJugada.PERDEDORA
            j.premio = 0.0

    pozo_pagado = 0.0
    if ganadoras:
        premio_unitario = sorteo.premio_fijo or 0.0
        for j in ganadoras:
            j.estado = EstadoJugada.GANADORA
            j.premio = premio_unitario
        pozo_pagado = round(premio_unitario * len(ganadoras), 2)
        # En rifa NO se limpia el pozo: el excedente queda para la casa.

    sorteo.estado = EstadoSorteo.LIQUIDADO
    return {
        "sorteo_id": sorteo.id,
        "modalidad": sorteo.modalidad,
        "horario": sorteo.horario,
        "jugadas_aprobadas": len(aprobadas),
        "ganadoras": [j.id for j in ganadoras],
        "pozo_pagado": round(pozo_pagado, 2),
        "pozo_sin_ganador": 0.0 if ganadoras else round((sorteo.pozo_cubierto or 0.0) + (sorteo.pozo_extra or 0.0), 2),
    }
