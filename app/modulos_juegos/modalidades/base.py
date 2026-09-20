class ModalidadBase:
    """Contrato que cumple toda modalidad de juego."""

    clave = ""
    nombre = ""
    resumen_reglas = ""
    cantidad_numeros = 0
    permite_repetidos = False
    requiere_pozo = True
    usa_premio_fijo = False

    def gana(self, numeros_jugada, resultados) -> bool:
        """Regla de victoria: por defecto, todos los numeros en los resultados."""
        return bool(resultados) and set(numeros_jugada).issubset(resultados)

    def calcular_premio(self, jugadas_ganadoras, pozo_actual, premio_fijo) -> float:
        """Calcula el premio por jugada ganadora."""
        if not jugadas_ganadoras:
            return 0.0
        if self.usa_premio_fijo:
            return premio_fijo or 0.0
        return round(pozo_actual / len(jugadas_ganadoras), 2)
