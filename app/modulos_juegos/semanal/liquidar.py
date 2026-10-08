"""Liquidacion de SEMANAL, independiente del motor general.

Usa el plugin.gana() de la modalidad contra los acumulados y reparte el pozo.
"""

from app.modelos.juegos import EstadoJugada, EstadoSorteo, Jugada
from app.modulos_juegos.modalidades import obtener


def liquidar_sorteo_semanal(sorteo, sesion, reglas) -> dict:
    plugin = obtener(sorteo.modalidad)
    resultados = sorteo.lista_resultados
    aprobadas = (
        sesion.query(Jugada)
        .filter(Jugada.sorteo_id == sorteo.id, Jugada.estado == EstadoJugada.APROBADA)
        .all()
    )
    ganadoras = []
    for j in aprobadas:
        if plugin and plugin.gana(j.lista_numeros, resultados):
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
