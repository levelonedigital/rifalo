"""Registro de ciclos de vida por modalidad de sorteo.

Cada modalidad puede tener su propio ciclo (preventivo + cancelacion automatica).
El buscador consulta este registro para delegar el comportamiento especifico.
Si una modalidad no tiene ciclo propio, el buscador usa su comportamiento generico.
"""

from app.modulos_juegos.rifa import ciclo as rifa_ciclo

REGISTRO_CICLO = {
    "rifa": rifa_ciclo,
}


def obtener_ciclo(modalidad: str):
    """Devuelve el modulo de ciclo de la modalidad, o None si no tiene."""
    return REGISTRO_CICLO.get(modalidad)
