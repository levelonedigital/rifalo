from app.modulos_juegos.modalidades.base import ModalidadBase


class ModalidadClasico(ModalidadBase):
    clave = "clasico"
    nombre = "Clasico"
    resumen_reglas = "3 numeros de 2 cifras, sin repetir. Gana si los 3 estan entre los 20 del sorteo."
    cantidad_numeros = 3
    permite_repetidos = False
    requiere_pozo = True
    usa_premio_fijo = False
