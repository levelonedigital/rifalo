"""Cobertura de la meta en SEMANAL: cuanto hay que juntar y cuanto se junto."""


def meta_cobertura_semanal(sorteo) -> float:
    if sorteo.minimo_cubrir is not None:
        return sorteo.minimo_cubrir
    return sorteo.pozo_base or 0.0


def acumulado_cobertura_semanal(sorteo) -> float:
    return (sorteo.pozo_cubierto or 0.0) + (sorteo.pozo_extra or 0.0)


def cubre_meta_semanal(sorteo) -> bool:
    return acumulado_cobertura_semanal(sorteo) >= meta_cobertura_semanal(sorteo)
