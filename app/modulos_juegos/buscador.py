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
from app.modelos.juegos import Aviso, EstadoSorteo, Sorteo

_intentos = {}  # {sorteo_id: {"primero": datetime, "lecturas": [lista_nums, ...]}}


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


def costo_a_cubrir(sorteo: Sorteo) -> float:
    """Costo de referencia del sorteo: minimo explicito, premio fijo (rifa) o pozo inicial."""
    if sorteo.minimo_cubrir is not None:
        return sorteo.minimo_cubrir
    if sorteo.modalidad == "rifa":
        return sorteo.premio_fijo or 0.0
    return sorteo.pozo_inicial or 0.0


def chequeo_costo(sesion, reglas, ahora: datetime):
    """A 30 minutos del horario oficial, avisa al admin si el recaudado no cubre el costo."""
    pendientes = (
        sesion.query(Sorteo)
        .filter(
            Sorteo.estado == EstadoSorteo.PROGRAMADO,
            Sorteo.aviso_costo_enviado.is_(False),
        )
        .all()
    )
    for sorteo in pendientes:
        hhmm = reglas.dict_horarios().get(sorteo.horario)
        if not hhmm:
            continue
        hora, minuto = (int(x) for x in hhmm.split(":"))
        momento = sorteo.fecha.replace(hour=hora, minute=minuto, second=0, microsecond=0)
        if momento - timedelta(minutes=30) <= ahora < momento:
            costo = costo_a_cubrir(sorteo)
            if (sorteo.recaudado or 0.0) < costo:
                aviso = Aviso(
                    texto=(
                        f"ADMIN: sorteo #{sorteo.id} ({sorteo.modalidad} {sorteo.horario}) no cubre el costo: "
                        f"recaudado ${(sorteo.recaudado or 0.0):.2f} de ${costo:.2f}. Decidi si reprogramas el horario."
                    ),
                    destino="admin",
                )
                sesion.add(aviso)
                sorteo.aviso_costo_enviado = True
                sesion.commit()


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
    """Una pasada: cierre automatico, alerta de costo y busqueda con triple check."""
    sesion = SessionLocal()
    try:
        reglas = obtener_reglas(sesion)
        horarios = reglas.dict_horarios()
        ahora = datetime.now()
        chequeo_costo(sesion, reglas, ahora)

        # 1) CIERRE AUTOMATICO: al llegar el horario oficial, el sorteo se cierra solo.
        programados = (
            sesion.query(Sorteo)
            .filter(Sorteo.estado == EstadoSorteo.PROGRAMADO, Sorteo.modalidad != "semanal")
            .all()
        )
        for sorteo in programados:
            hhmm = horarios.get(sorteo.horario)
            if not hhmm:
                continue
            hora, minuto = (int(x) for x in hhmm.split(":"))
            momento = sorteo.fecha.replace(hour=hora, minute=minuto, second=0, microsecond=0)
            if ahora >= momento:
                sorteo.estado = EstadoSorteo.CERRADO
                auditoria.registrar(sesion, "SORTEO_CERRADO_AUTO", detalle=f"sorteo={sorteo.id} horario={sorteo.horario}")
                sesion.commit()

        # 2) BUSQUEDA AUTOMATICA con TRIPLE CHECK en sorteos cerrados sin resultado.
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
            if ahora < momento + timedelta(minutes=reglas.busqueda_inicio_min or 5):
                continue
            
            estado = _intentos.setdefault(sorteo.id, {"primero": ahora, "lecturas": []})
            
            # Leer números de la página oficial
            numeros = obtener_resultado_oficial(sorteo.horario)
            if numeros:
                estado["lecturas"].append(numeros)
                
                # TRIPLE CHECK: solo liquidar si los últimos 3 intentos dieron los mismos números
                if len(estado["lecturas"]) >= 3:
                    ultimas_tres = estado["lecturas"][-3:]
                    if ultimas_tres[0] == ultimas_tres[1] == ultimas_tres[2]:
                        # Confirmado: los 3 intentos coinciden
                        sorteo.resultados = ",".join(f"{n:02d}" for n in numeros)
                        auditoria.registrar(sesion, "RESULTADO_AUTOMATICO", detalle=f"sorteo={sorteo.id} nums={sorteo.resultados} (confirmado en 3 lecturas)")
                        sesion.commit()
                        resumen = liquidar_sorteo(sorteo, sesion, reglas)
                        auditoria.registrar(sesion, "SORTEO_LIQUIDADO", detalle=str(resumen))
                        sesion.commit()
                        _actualizar_semanal(sesion, sorteo, reglas)
                        _intentos.pop(sorteo.id, None)
                    else:
                        # No coinciden: limpiar y seguir reintentando
                        estado["lecturas"] = [numeros]
                        auditoria.registrar(sesion, "RESULTADO_INCONSISTENTE", detalle=f"sorteo={sorteo.id}: numeros varian entre lecturas, reintentando")
                        sesion.commit()
            
            # Si pasó la ventana de tiempo sin confirmar, avisar al admin
            elif ahora - estado["primero"] > timedelta(minutes=reglas.busqueda_duracion_min or 30):
                sorteo.busqueda_agotada = True
                aviso = Aviso(
                    texto=(
                        f"ADMIN: sorteo #{sorteo.id} ({sorteo.modalidad} {sorteo.horario}): "
                        f"no se encontro el resultado oficial automaticamente. Carga los 20 numeros manualmente."
                    ),
                    destino="admin",
                )
                sesion.add(aviso)
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
