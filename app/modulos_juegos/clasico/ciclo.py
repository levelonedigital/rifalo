"""Ciclo propio de CLASICO: preventivo antes del cierre y cancelacion automatica al cierre.

Independiente de rifa y de semanal. Lee su meta y su acumulado de cobertura.py.
"""
from datetime import timedelta

from app.modelos.juegos import Aviso

from app.modulos_juegos.clasico.cobertura import (
    acumulado_cobertura_clasico,
    meta_cobertura_clasico,
)


def chequeo_preventivo(sorteo, sesion, reglas, ahora, momento_cierre) -> bool:
    """60 min antes del cierre, avisa SOLO al admin si va por debajo de la meta."""
    if sorteo.aviso_costo_enviado:
        return False
    if ahora < momento_cierre - timedelta(minutes=60):
        return False
    if ahora >= momento_cierre:
        return False
    meta = meta_cobertura_clasico(sorteo)
    acum = acumulado_cobertura_clasico(sorteo)
    if acum < meta:
        aviso = Aviso(
            texto=(
                f"ADMIN: sorteo #{sorteo.id} (clasico {sorteo.horario}) va por debajo del minimo: "
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
    """Al cerrar, si el acumulado no llego a la meta, el clasico se reprograma."""
    return acumulado_cobertura_clasico(sorteo) < meta_cobertura_clasico(sorteo)


def mensaje_reprogramacion(sorteo) -> str:
    return (
        f"Sorteo #{sorteo.id} ({sorteo.modalidad} {sorteo.horario} {sorteo.fecha.strftime('%d/%m')}): "
        f"jugada cancelada por no cumplir los requisitos. Se reprograma para otra fecha/horario. "
        f"Tus jugadas y números quedan reservados."
    )
