from app.modulos_juegos.modalidades.base import ModalidadBase


class ModalidadClasico(ModalidadBase):
    clave = "clasico"
    nombre = "Clasico"
    resumen_reglas = (
        "Se eligen 3 numeros de 2 cifras por jugada. En una misma jugada no puede repetirse un numero; "
        "distintos jugadores si pueden elegir la misma combinacion. "
        "Gana si los 3 numeros estan entre los 20 del sorteo del horario elegido. "
        "Si hay mas de 1 ganador l pozo se reparte en partes iguales entre los ganadores."
    )
    cantidad_numeros = 3
    permite_repetidos = False
    requiere_pozo = True
    usa_premio_fijo = False
    auto_vacante = False
