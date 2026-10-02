"""Registro de modalidades: ahora se llena por descubrimiento automatico.

Ya no hay lista manual: el descubrimiento escanea las carpetas de modulos_juegos que
tienen plugin.py y las registra. Agregar una modalidad nueva no requiere tocar este
archivo ni ningun otro: se descubre sola al arrancar.
"""
from app.modulos_juegos import descubrimiento

REGISTRO = descubrimiento.plugins()


def obtener(clave: str):
    """Devuelve la instancia del plugin de la modalidad, o None."""
    return descubrimiento.obtener_plugin(clave)


def listar():
    """Devuelve todas las modalidades descubiertas con su resumen."""
    return descubrimiento.listar_modalidades()
