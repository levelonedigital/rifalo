from app.modulos_juegos.modalidades.base import ModalidadBase


class ModalidadClasico(ModalidadBase):
    """Modalidad CLASICO: logica propia, independiente de rifa y semanal."""

    clave = "clasico"
    nombre = "Clasico"
    resumen_reglas = (
        "Se eligen 3 numeros de 2 cifras por jugada. En una misma jugada no puede repetirse un numero; "
        "distintos jugadores si pueden elegir la misma combinacion. "
        "Gana si los 3 numeros estan entre los 20 del sorteo del horario elegido. "
        "Si hay mas de 1 ganador el pozo se reparte en partes iguales entre los ganadores."
    )
    cantidad_numeros = 3
    permite_repetidos = False
    requiere_pozo = True
    usa_premio_fijo = False
    auto_vacante = False
    oculta = False

    def gana(self, numeros_jugada, resultados) -> bool:
        """Gana si todos los numeros de la jugada estan entre los 20 del sorteo."""
        return bool(resultados) and set(numeros_jugada).issubset(resultados)

    def calcular_premio(self, jugadas_ganadoras, pozo_actual, premio_fijo) -> float:
        """El pozo se reparte en partes iguales entre las ganadoras."""
        if not jugadas_ganadoras:
            return 0.0
        return round(pozo_actual / len(jugadas_ganadoras), 2)
