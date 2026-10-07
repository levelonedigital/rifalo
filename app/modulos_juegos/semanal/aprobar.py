"""Reparto de una jugada de SEMANAL, independiente del motor general.

Igual esquema que clasico: el sobrante cubre el pozo base primero, y el excedente
suma como pozo_extra. Semanal no cierra por horario (se liquida al fin del rango de
dias), asi que no trae ciclo.py de preventivo/cancelacion.
"""

from app.modelos.juegos import EstadoJugada, Sorteo
from app.modelos.usuario import Usuario

from app.modulos_juegos.semanal.cobertura import meta_cobertura_semanal


def _porcentajes(sorteo: Sorteo, reglas):
    casa = sorteo.casa_pct if sorteo.casa_pct is not None else 30.0
    linea = sorteo.vendedor_pct if sorteo.vendedor_pct is not None else reglas.vendedor_pct
    pozo = max(0.0, 100.0 - casa - linea)
    return casa, linea, pozo


def aprobar_jugada_semanal(sesion, jugada, reglas):
    sorteo = sesion.get(Sorteo, jugada.sorteo_id)
    vendedor = sesion.get(Usuario, jugada.vendedor_id)
    revendedor = sesion.get(Usuario, jugada.revendedor_id) if jugada.revendedor_id else None

    casa_pct, linea_pct, pozo_pct = _porcentajes(sorteo, reglas)

    vend_efectivo = linea_pct
    if vendedor is not None and vendedor.comision_pct is not None:
        vend_efectivo = min(vendedor.comision_pct, linea_pct)
    rev_pct = 0.0
    if revendedor is not None:
        rev_pct = min(revendedor.comision_pct or 0.0, vend_efectivo)

    precio = jugada.precio
    base = meta_cobertura_semanal(sorteo)
    sorteo.recaudado = (sorteo.recaudado or 0.0) + precio

    sobrante = round(precio * pozo_pct / 100.0, 2)

    aporte_cubrir = 0.0
    aporte_extra = 0.0
    if sobrante > 0:
        cubierto_previo = sorteo.pozo_cubierto or 0.0
        if cubierto_previo >= base:
            aporte_extra = sobrante
        else:
            faltante = base - cubierto_previo
            aporte_cubrir = round(min(sobrante, faltante), 2)
            aporte_extra = round(sobrante - aporte_cubrir, 2)

    sorteo.pozo_cubierto = round((sorteo.pozo_cubierto or 0.0) + aporte_cubrir, 2)
    sorteo.pozo_extra = round((sorteo.pozo_extra or 0.0) + aporte_extra, 2)

    monto_rev = round(precio * rev_pct / 100.0, 2)
    monto_vend = round(precio * vend_efectivo / 100.0, 2) - monto_rev
    monto_casa = round(precio - monto_rev - monto_vend - aporte_extra - aporte_cubrir, 2)

    jugada.estado = EstadoJugada.APROBADA
    jugada.monto_casa = monto_casa
    jugada.monto_vendedor = monto_vend
    jugada.monto_revendedor = monto_rev
    jugada.monto_pozo = aporte_extra
    jugada.monto_cubrir = aporte_cubrir
    return jugada
