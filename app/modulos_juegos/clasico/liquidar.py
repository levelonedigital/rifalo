"""Liquidacion de CLASICO, independiente del motor general.

Compara los 3 numeros de cada jugada contra los 20 del sorteo. Gana si los 3 estan.
El pozo (inicial + extra) se reparte en partes iguales entre las ganadoras. Al pagar,
el pozo se limpia (queda en 0 para el proximo ciclo o el vacante).
"""

from app.modelos.juegos import EstadoJugada, EstadoSorteo, Jugada


def liquidar_sorteo_clasico(sorteo, sesion, reglas) -> dict:
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
        # En clasico el pozo se paga entero: se limpia despues de liquidar.
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
