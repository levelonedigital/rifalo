from app.modulos_juegos.modalidades.base import ModalidadBase


class ModalidadSemanal(ModalidadBase):
    clave = "semanal"
    nombre = "Semanal"
    resumen_reglas = (
        "10 numeros de 2 cifras por jugada. En una misma jugada no puede repetirse un numero; "
        "distintos jugadores si pueden elegir la misma combinacion. "
        "Gana si los 10 estan entre los numeros acumulados de los sorteos del horario semanal "
        "en los 5 dias de la ventana. "
        "El pozo se reparte en partes iguales entre los ganadores. "
        "Si no hay ganadores, el pozo queda retenido y el admin decide: "
        "pozo vacante para los del original o arrancar de cero."
    )
    cantidad_numeros = 10
    permite_repetidos = False
    requiere_pozo = True
    usa_premio_fijo = False
    auto_vacante = False
