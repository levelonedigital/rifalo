"""Ciclo propio de RIFA: preventivo antes del cierre y cancelacion automatica al cierre.

El buscador general delega aca cuando la modalidad tiene ciclo propio. Rifa decide
sus reglas; clasico y semanal no se enteran.
"""

from datetime import timedelta

from app.modelos.juegos import Aviso

from app.modulos_juegos.rifa.cobertura import acumulado_cobertura_rifa, meta_cobertura_rifa


def chequeo_preventivo(sorteo, sesion, reglas, ahora, momento_cierre) -> bool:
    """60 min antes del cierre, avisa SOLO al admin si va por debajo de la meta.
    No cancela: todavia se puede vender."""
    if sorteo.aviso_costo_enviado:
        return False
    if ahora < momento_cierre - timedelta(minutes=60):
        return False
    if ahora >= momento_cierre:
        return False
    meta = meta_cobertura_rifa(sorteo)
    acum = acumulado_cobertura_rifa(sorteo)
    if acum < meta:
        aviso = Aviso(
            texto=(
                f"ADMIN: sorteo #{sorteo.id} (rifa {sorteo.horario}) va por debajo del minimo: "
                f"acumulado ${acum:.2f} de ${meta:.2f}. Si al cierre no llega, se reprogramara automaticamente."
            ),
            destino="admin",
        )
        sesion.add(aviso)
        sorteo.aviso_costo_enviado = True
        sesion.commit()
        return True
    return False


def debe_cancelar_al_cierre(sorteo, sesion, reglas) -> bool:
    """Al cerrar, si el acumulado no llego a la meta, la rifa se reprograma."""
    return acumulado_cobertura_rifa(sorteo) < meta_cobertura_rifa(sorteo)


def mensaje_reprogramacion(sorteo) -> str:
    return (
        f"Sorteo #{sorteo.id} ({sorteo.modalidad} {sorteo.horario} {sorteo.fecha.strftime('%d/%m')}): "
        f"jugada cancelada por no cumplir los requisitos. Se reprograma para otra fecha/horario. "
        f"Tus jugadas y números quedan reservados."
    )
