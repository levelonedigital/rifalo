from app.modulos_juegos.modalidades.base import ModalidadBase


class ModalidadRifa(ModalidadBase):
    """Modalidad RIFA: logica propia, independiente de clasico y semanal."""

    clave = "rifa"
    nombre = "Rifa"
    resumen_reglas = "1 numero de 2 cifras. Gana si coincide con los ultimos 2 digitos del 1er premio del sorteo (el resultado oficial es de 4 cifras)."
    cantidad_numeros = 1
    permite_repetidos = True
    requiere_pozo = False
    usa_premio_fijo = True
    auto_vacante = False
    oculta = False

    def gana(self, numeros_jugada, resultados) -> bool:
        """Gana solo si el numero del jugador coincide con los ultimos 2 digitos del 1er premio."""
        if not resultados or not numeros_jugada:
            return False
        return numeros_jugada[0] == (resultados[0] % 100)
