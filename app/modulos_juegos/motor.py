from sqlalchemy.orm import Session

from app.core.config import Configuracion
from app.modelos.juegos import EstadoJugada, EstadoSorteo, Jugada, ModuloJuego, Sorteo


def liquidar_sorteo(sorteo: Sorteo, sesion: Session) -> dict:
    """Calcula ganadoras y premios segun el modulo del sorteo.

    Reglas:
    - CLASICO: cada jugada ganadora cobra monto * PAGO_PLENO_NUMERO.
    - RIFA: el ticket ganador cobra el premio fijo del sorteo.
    - SEMANAL: el pozo (acumulado + recaudado) se reparte entre ganadores.
      Si no hay ganadores, el pozo queda para la proxima semana.
    No hace commit: lo hace quien llama.
    """
    aprobadas = (
        sesion.query(Jugada)
        .filter(Jugada.sorteo_id == sorteo.id, Jugada.estado == EstadoJugada.APROBADA)
        .all()
    )
    ganadoras = []
    total_premios = 0.0

    if sorteo.modulo == ModuloJuego.SEMANAL:
        pozo = (sorteo.pozo_acumulado or 0.0) + sum(j.monto for j in aprobadas)
        acertadas = [j for j in aprobadas if j.numero == sorteo.resultado_numero]
        if acertadas:
            parte = round(pozo / len(acertadas), 2)
            for j in aprobadas:
                if j.numero == sorteo.resultado_numero:
                    j.estado = EstadoJugada.GANADORA
                    j.premio = parte
                else:
                    j.estado = EstadoJugada.PERDEDORA
                    j.premio = 0.0
            sorteo.pozo_acumulado = 0.0
            ganadoras = acertadas
            total_premios = round(parte * len(acertadas), 2)
        else:
            for j in aprobadas:
                j.estado = EstadoJugada.PERDEDORA
                j.premio = 0.0
            sorteo.pozo_acumulado = pozo
    else:
        for j in aprobadas:
            if j.numero == sorteo.resultado_numero:
                j.estado = EstadoJugada.GANADORA
                if sorteo.modulo == ModuloJuego.CLASICO:
                    j.premio = round(j.monto * Configuracion.PAGO_PLENO_NUMERO, 2)
                else:
                    j.premio = sorteo.premio_fijo or 0.0
                ganadoras.append(j)
                total_premios += j.premio
            else:
                j.estado = EstadoJugada.PERDEDORA
                j.premio = 0.0

    sorteo.estado = EstadoSorteo.LIQUIDADO
    return {
        "sorteo_id": sorteo.id,
        "modulo": sorteo.modulo.value,
        "resultado": sorteo.resultado_numero,
        "jugadas_aprobadas": len(aprobadas),
        "ganadoras": len(ganadoras),
        "total_premios": round(total_premios, 2),
        "pozo_restante": round(sorteo.pozo_acumulado or 0.0, 2),
    }
