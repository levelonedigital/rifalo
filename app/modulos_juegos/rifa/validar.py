"""Validacion de numeros propios de RIFA (numeros unicos entre jugadas)."""

from app.modelos.juegos import EstadoJugada, Jugada
from app.modulos_juegos.modalidades import obtener

ESTADOS_ACTIVAS_RIFA = [EstadoJugada.PENDIENTE, EstadoJugada.APROBADA]


def es_rifa_numero_unico(sorteo) -> bool:
    modalidad = obtener(sorteo.modalidad)
    return bool(modalidad and modalidad.usa_premio_fijo and modalidad.cantidad_numeros == 1)


def numeros_ocupados_rifa(sesion, sorteo):
    """Lista de numeros ya jugados (pendientes o aprobados). None si no aplica."""
    if not es_rifa_numero_unico(sorteo):
        return None
    jugadas = (
        sesion.query(Jugada)
        .filter(Jugada.sorteo_id == sorteo.id, Jugada.estado.in_(ESTADOS_ACTIVAS_RIFA))
        .all()
    )
    ocupados = set()
    for j in jugadas:
        for n in j.lista_numeros:
            ocupados.add(n)
    return sorted(ocupados)


def validar_numeros_rifa(sesion, sorteo, numeros) -> None:
    """Rechaza si algun numero ya esta jugado en esta rifa."""
    ocupados = numeros_ocupados_rifa(sesion, sorteo)
    if ocupados is None:
        return
    for n in numeros:
        if n in ocupados:
            raise ValueError(f"El numero {n:02d} ya esta jugado en este sorteo; elegi otro")
