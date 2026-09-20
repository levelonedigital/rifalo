import re
import threading
import time
import unicodedata
from datetime import datetime, timedelta

import requests

from app.core import auditoria
from app.core.config import Configuracion
from app.core.database import SessionLocal
from app.modulos_juegos.motor import liquidar_sorteo, obtener_reglas
from app.modelos.juegos import EstadoSorteo, Sorteo

_intentos = {}


def _normalizar(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texto.upper()) if unicodedata.category(c) != "Mn"
    )


def obtener_resultado_oficial(nombre_horario: str):
    """Best-effort: lee los 20 numeros del horario en la web oficial."""
    try:
        respuesta = requests.get(
            Configuracion.URL_QUINIELA,
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"},
        )
        texto = respuesta.text
        indice = _normalizar(texto).find(_normalizar(nombre_horario))
        if indice < 0:
            return None
        chunk = texto[indice:indice + 6000]
        nums = re.findall(r">\s*(\d{2})\s*<", chunk)
        if len(nums) < 20:
            nums = re.findall(r"\b(\d{2})\b", chunk)
        nums = nums[:20]
        if len(nums) < 20:
            return None
        return [int(n) for n in nums]
    except Exception:
        return None


def _actualizar_semanal(sesion, sorteo_dia: Sorteo, reglas):
    """Acumula los numeros del dia al pozo semanal y lo liquida al cerrar la ventana."""
    if sorteo_dia.horario != reglas.semanal_horario:
        return
    dia = sorteo_dia.fecha.weekday()
    if not (reglas.semanal_dia_inicio <= dia <= reglas.semanal_dia_fin):
        return
    semanal = (
        sesion.query(Sorteo)
        .filter(Sorteo.modalidad == "semanal", Sorteo.estado != EstadoSorteo.LIQUIDADO)
        .order_by(Sorteo.id.desc())
        .first()
    )
    if semanal is None:
        return
    acumulados = set(semanal.lista_resultados)
    acumulados.update(sorteo_dia.lista_resultados)
    semanal.resultados = ",".join(f"{n:02d}" for n in sorted(acumulados))
    sesion.commit()
    if dia >= reglas.semanal_dia_fin:
        resumen = liquidar_sorteo(semanal, sesion, reglas)
        auditoria.registrar(sesion, "SEMANAL_LIQUIDADO", detalle=str(resumen))
        sesion.commit()


def ciclo():
    """Una pasada de busqueda: revisa sorteos cerrados sin resultado."""
    sesion = SessionLocal()
    try:
        reglas = obtener_reglas(sesion)
        horarios = reglas.dict_horarios()
        ahora = datetime.now()
        pendientes = (
            sesion.query(Sorteo)
            .filter(
                Sorteo.estado == EstadoSorteo.CERRADO,
                Sorteo.resultados.is_(None),
                Sorteo.busqueda_agotada.is_(False),
                Sorteo.modalidad != "semanal",
            )
            .all()
        )
        for sorteo in pendientes:
            hhmm = horarios.get(sorteo.horario)
            if not hhmm:
                continue
            hora, minuto = (int(x) for x in hhmm.split(":"))
            momento = sorteo.fecha.replace(hour=hora, minute=minuto, second=0, microsecond=0)
            if ahora < momento + timedelta(minutes=reglas.busqueda_inicio_min or 1):
                continue
            estado = _intentos.setdefault(sorteo.id, {"primero": ahora, "ultimo": None})
            if estado["ultimo"] and ahora - estado["ultimo"] < timedelta(minutes=reglas.busqueda_intervalo_min or 2):
                continue
            estado["ultimo"] = ahora
            numeros = obtener_resultado_oficial(sorteo.horario)
            if numeros:
                sorteo.resultados = ",".join(f"{n:02d}" for n in numeros)
                auditoria.registrar(sesion, "RESULTADO_AUTOMATICO", detalle=f"sorteo={sorteo.id} nums={sorteo.resultados}")
                sesion.commit()
                resumen = liquidar_sorteo(sorteo, sesion, reglas)
                auditoria.registrar(sesion, "SORTEO_LIQUIDADO", detalle=str(resumen))
                sesion.commit()
                _actualizar_semanal(sesion, sorteo, reglas)
                _intentos.pop(sorteo.id, None)
            elif ahora - estado["primero"] > timedelta(minutes=reglas.busqueda_duracion_min or 16):
                sorteo.busqueda_agotada = True
                auditoria.registrar(sesion, "BUSQUEDA_AGOTADA", detalle=f"sorteo={sorteo.id}: requiere carga manual")
                sesion.commit()
                _intentos.pop(sorteo.id, None)
    finally:
        sesion.close()


def iniciar_buscador():
    """Hilo de fondo que corre un ciclo cada 20 segundos."""
    def bucle():
        while True:
            try:
                ciclo()
            except Exception:
                pass
            time.sleep(20)
    hilo = threading.Thread(target=bucle, daemon=True)
    hilo.start()
    return hilo
