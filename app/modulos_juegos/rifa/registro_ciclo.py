"""Directorio de ciclos por modalidad: el buscador pregunta aca quien maneja el
cierre/cancelacion de cada modalidad. Si una modalidad no tiene ciclo propio,
el buscador usa su comportamiento general (clasico y semanal por ahora)."""

from app.modulos_juegos.rifa import ciclo as ciclo_rifa

REGISTRO_CICLO = {
    "rifa": ciclo_rifa,
}


def obtener_ciclo(clave: str):
    return REGISTRO_CICLO.get(clave)
