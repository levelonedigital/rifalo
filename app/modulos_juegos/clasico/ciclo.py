"""Ciclo propio de CLASICO: preventivo antes del cierre y cancelacion automatica al cierre.

La meta de clasico es el pozo inicial (o minimo_cubrir si el admin lo pisa).
El acumulado es la suma de sobrantes (pozo_cubierto + pozo_extra).
Independiente de rifa y de semanal.
"""
from datetime import timedelta

from app.modelos.juegos import Aviso


def meta_cobertura_clasico(sorteo) -> float:
    if sorteo.minimo_cubrir is not None:
        return sorteo.minimo_cubrir
    return sorteo.pozo_inicial or 0.0


def acumulado_cobertura_clasico(sorteo) -> float:
    return (sorteo.pozo_cubierto or 0.0) + (sorteo.pozo_extra or 0.0)


def chequeo_preventivo(sorteo, sesion, reglas, ahora, momento_cierre) -> bool:
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
    return acumulado_cobertura_clasico(sorteo) < meta_cobertura_clasico(sorteo)


def mensaje_reprogramacion(sorteo) -> str:
    return (
        f"Sorteo #{sorteo.id} ({sorteo.modalidad} {sorteo.horario} {sorteo.fecha.strftime('%d/%m')}): "
        f"jugada cancelada por no cumplir los requisitos. Se reprograma para otra fecha/horario. "
        f"Tus jugadas y números quedan reservados."
    )
