"""Ciclo de vida de SEMANAL.

El semanal no cierra por horario: se alimenta acumulando los numeros de los sorteos
diarios del mismo horario que caen dentro del rango de dias, y se liquida al llegar
al dia fin. La funcion alimentar_desde_diario es detectada por el descubrimiento como
hook y llamada por el buscador luego de liquidar cada sorteo diario.
"""


def alimentar_desde_diario(sesion, sorteo_dia, reglas):
    from app.core import auditoria
    from app.modelos.juegos import EstadoSorteo, Sorteo
    from app.modulos_juegos.motor import liquidar_sorteo

    dia = sorteo_dia.fecha.weekday()
    semanal = (
        sesion.query(Sorteo)
        .filter(
            Sorteo.modalidad == "semanal",
            Sorteo.estado != EstadoSorteo.LIQUIDADO,
            Sorteo.horario == sorteo_dia.horario,
        )
        .order_by(Sorteo.id.desc())
        .first()
    )
    if semanal is None:
        return
    ini = semanal.semanal_dia_inicio if semanal.semanal_dia_inicio is not None else (reglas.semanal_dia_inicio or 0)
    fin = semanal.semanal_dia_fin if semanal.semanal_dia_fin is not None else (reglas.semanal_dia_fin or 4)
    if not (ini <= dia <= fin):
        return
    acumulados = set(semanal.lista_resultados)
    acumulados.update(sorteo_dia.lista_resultados)
    semanal.resultados = ",".join(f"{n:02d}" for n in sorted(acumulados))
    sesion.commit()
    if dia >= fin:
        resumen = liquidar_sorteo(semanal, sesion, reglas)
        auditoria.registrar(sesion, "SEMANAL_LIQUIDADO", detalle=str(resumen))
        sesion.commit()
