from app.modulos_juegos.modalidades.base import ModalidadBase


class ModalidadSemanal(ModalidadBase):
    clave = "semanal"
    nombre = "Semanal"
    resumen_reglas = "10 numeros de 2 cifras, sin repetir. Gana si los 10 estan entre los numeros acumulados de la semana."
    cantidad_numeros = 10
    permite_repetidos = False
    requiere_pozo = True
    usa_premio_fijo = False
