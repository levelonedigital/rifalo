"""Liquidacion de RIFA, independiente del motor general.

Usa el plugin.gana() de la modalidad para decidir ganadores (logica en un solo lugar).
Las ganadoras cobran el premio fijo. El excedente del acumulado queda para la casa.
"""

from app.modelos.juegos import EstadoJugada, EstadoSorteo, Jugada
from app.modulos_juegos.modalidades import obtener


def liquidar_sorteo_rifa(sorteo, sesion, reglas) -> dict:
    plugin = obtener(sorteo.modalidad)
    resultados = sorteo.lista_resultados
    aprobadas = (
        sesion.query(Jugada)
        .filter(Jugada.sorteo_id == sorteo.id, Jugada.estado == EstadoJugada.APROBADA)
        .all()
    )
    ganadoras = []
    for j in aprobadas:
        numeros = j.lista_numeros
        if plugin and plugin.gana(numeros, resultados):
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
