"""Cobertura de la meta en CLASICO: cuanto hay que juntar y cuanto se junto.

La meta de clasico es el pozo base (lo que el admin carga como 'pozo base / minimo a
cubrir'), o minimo_cubrir si el admin lo pisa. El acumulado es la suma de sobrantes
(pozo_cubierto + pozo_extra).
"""


def meta_cobertura_clasico(sorteo) -> float:
    if sorteo.minimo_cubrir is not None:
        return sorteo.minimo_cubrir
    return sorteo.pozo_base or 0.0


def acumulado_cobertura_clasico(sorteo) -> float:
    return (sorteo.pozo_cubierto or 0.0) + (sorteo.pozo_extra or 0.0)


def cubre_meta_clasico(sorteo) -> bool:
    return acumulado_cobertura_clasico(sorteo) >= meta_cobertura_clasico(sorteo)
