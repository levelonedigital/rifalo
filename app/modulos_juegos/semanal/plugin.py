from app.modulos_juegos.modalidades.base import ModalidadBase


class ModalidadSemanal(ModalidadBase):
    """Modalidad SEMANAL: logica propia, independiente de rifa y clasico.

    cierra_por_horario=False: el semanal no cierra a una hora; se alimenta de los
    sorteos diarios y se liquida al llegar al dia fin del rango.
    """

    clave = "semanal"
    nombre = "Semanal"
    resumen_reglas = (
        "Se eligen 10 numeros de 2 cifras por jugada. En una misma jugada no puede repetirse un numero; "
        "distintos jugadores si pueden elegir la misma combinacion. "
        "Gana si los 10 estan entre los numeros acumulados de los sorteos del horario semanal "
        "en los 5 dias de la ventana. "
        "Si hay mas de 1 ganador el pozo se reparte en partes iguales entre los ganadores."
    )
    cantidad_numeros = 10
    permite_repetidos = False
    requiere_pozo = True
    usa_premio_fijo = False
    auto_vacante = False
    oculta = False
    cierra_por_horario = False

    def gana(self, numeros_jugada, resultados) -> bool:
        return bool(resultados) and set(numeros_jugada).issubset(resultados)

    def calcular_premio(self, jugadas_ganadoras, pozo_actual, premio_fijo) -> float:
        if not jugadas_ganadoras:
            return 0.0
        return round(pozo_actual / len(jugadas_ganadoras), 2)
