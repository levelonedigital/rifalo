from app.modulos_juegos.modalidades.base import ModalidadBase


class ModalidadSemanal(ModalidadBase):
    clave = "semanal"
    nombre = "Semanal"
    resumen_reglas = (
        "Se eligen 10 numeros de 2 cifras por jugada. En una misma jugada no puede repetirse un numero; "
        "distintos jugadores si pueden elegir la misma combinacion. "
        "Gana si los 10 estan entre los numeros acumulados de los sorteos del horario semanal "
        "en los 5 dias de la ventana. "
        "Si hay mas de 1 Ganador el pozo se reparte en partes iguales entre los ganadores."
    )
    cantidad_numeros = 10
    permite_repetidos = False
    requiere_pozo = True
    usa_premio_fijo = False
    auto_vacante = False
