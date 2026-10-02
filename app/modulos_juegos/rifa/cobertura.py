"""Cobertura de la meta en RIFA: cuanto hay que juntar y cuanto se junto.

La meta de una rifa es el premio fijo (o el minimo_cubrir si el admin lo pisa).
El acumulado es la suma de los sobrantes de las jugadas (pozo_cubierto + pozo_extra).
"""


def meta_cobertura_rifa(sorteo) -> float:
    """Monto que hay que recaudar con sobrantes para que la rifa sea jugable."""
    if sorteo.minimo_cubrir is not None:
        return sorteo.minimo_cubrir
    return sorteo.premio_fijo or 0.0


def acumulado_cobertura_rifa(sorteo) -> float:
    """Cuanto se acumulo hasta ahora de sobrantes de jugadas."""
    return (sorteo.pozo_cubierto or 0.0) + (sorteo.pozo_extra or 0.0)


def cubre_meta_rifa(sorteo) -> bool:
    return acumulado_cobertura_rifa(sorteo) >= meta_cobertura_rifa(sorteo)
