from app.modulos_juegos.clasico.plugin import ModalidadClasico
from app.modulos_juegos.modalidades.semanal import ModalidadSemanal
from app.modulos_juegos.rifa.plugin import ModalidadRifa

REGISTRO = {
    ModalidadClasico.clave: ModalidadClasico(),
    ModalidadSemanal.clave: ModalidadSemanal(),
    ModalidadRifa.clave: ModalidadRifa(),
}


def obtener(clave: str):
    """Devuelve la instancia de la modalidad por su clave."""
    return REGISTRO.get(clave)


def listar():
    """Devuelve todas las modalidades disponibles con su resumen."""
    return [
        {
            "clave": m.clave,
            "nombre": m.nombre,
            "resumen_reglas": m.resumen_reglas,
            "cantidad_numeros": m.cantidad_numeros,
            "permite_repetidos": m.permite_repetidos,
            "requiere_pozo": m.requiere_pozo,
            "usa_premio_fijo": m.usa_premio_fijo,
            "oculta": getattr(m, "oculta", False),
        }
        for m in REGISTRO.values()
    ]
