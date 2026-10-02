"""Registro de ciclos de vida por modalidad de sorteo.

Cada modalidad con cierre por horario tiene su propio ciclo (preventivo + cancelacion
automatica). El buscador consulta este registro y delega; ninguna modalidad conoce a
las otras. El semanal no tiene ciclo porque no cierra por horario (se liquida al fin
del rango de dias).
"""

from app.modulos_juegos.clasico import ciclo as ciclo_clasico
from app.modulos_juegos.rifa import ciclo as ciclo_rifa

REGISTRO_CICLO = {
    "rifa": ciclo_rifa,
    "clasico": ciclo_clasico,
}


def obtener_ciclo(modalidad: str):
    """Devuelve el modulo de ciclo de la modalidad, o None si no tiene."""
    return REGISTRO_CICLO.get(modalidad)
