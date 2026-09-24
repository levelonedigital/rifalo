import re
import threading
import time
import unicodedata
from datetime import datetime, timedelta, timezone

import requests

from app.core import auditoria
from app.core.config import Configuracion
from app.core.database import SessionLocal
from app.modulos_juegos.motor import liquidar_sorteo, obtener_reglas
from app.modelos.juegos import Aviso, EstadoSorteo, Sorteo

_intentos = {}


def _zona():
    """Zona horaria oficial del sistema (Argentina). Con respaldo a UTC-3 fijo."""
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(Configuracion.ZONA_HORARIA)
    except Exception:
        return timezone(timedelta(hours=-3))


def _momento_horario(sorteo: Sorteo, hhmm: str) -> datetime:
    hora, minuto = (int(x) for x in hhmm.split(":"))
    f = sorteo.fecha
    return datetime(f.year, f.month, f.day, hora, minuto, 0, tzinfo=_zona())


def _momento_cierre(sorteo: Sorteo):
    if not sorteo.hora_cierre or ":" not in sorteo.hora_cierre:
        return None
    try:
        hora, minuto = (int(x) for x in sorteo.hora_cierre.split(":"))
    except ValueError:
        return None
    f = sorteo.fecha
    return datetime(f.year, f.month, f.day, hora, minuto, 0, tzinfo=_zona())


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


def estado_busquedas():
    """Devuelve el estado actual de todas las búsquedas en curso (para el endpoint de debug)."""
    resultado = {}
    for sorteo_id, estado in _intentos.items():
        lecturas = estado.get("lecturas", [])
        resultado[str(sorteo_id)] = {
            "primera_lectura": estado["primero"].isoformat() if estado.get("primero") else None,
            "cantidad_lecturas": len(lecturas),
            "ultima_lectura": lecturas[-1] if lecturas else None,
            "ultimas_tres": lecturas[-3:] if len(lecturas) >= 3 else lecturas,
            "coinciden_ultimas_tres": (
                len(lecturas) >= 3 and lecturas[-1] == lecturas[-2] == lecturas[-3]
            ),
        }
    return resultado


def costo_a_cubrir(sorteo: Sorteo) -> float:
    if sorteo.minimo_cubrir is not None:
        return sorteo.minimo_cubrir
    if sorteo.modalidad == "rifa":
        return sorteo.premio_fijo or 0.0
    return sorteo.pozo_inicial or 0.0


def chequeo_costo(sesion, reglas, ahora: datetime):
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
        momento = _momento_horario(sorteo, hhmm)
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
    """Una pasada: cierre automatico, alerta de costo y busqueda con triple check (hora de Argentina)."""
    sesion = SessionLocal()
    try:
        reglas = obtener_reglas(sesion)
        horarios = reglas.dict_horarios()
        ahora = datetime.now(_zona())
        chequeo_costo(sesion, reglas, ahora)

        # 1) CIERRE AUTOMATICO en la hora_cierre (o horario oficial si no tiene cierre).
        programados = (
            sesion.query(Sorteo)
            .filter(Sorteo.estado == EstadoSorteo.PROGRAMADO, Sorteo.modalidad != "semanal")
            .all()
        )
        for sorteo in programados:
            hhmm = horarios.get(sorteo.horario)
            if not hhmm:
                continue
            cierre = _momento_cierre(sorteo)
            if cierre is None:
                cierre = _momento_horario(sorteo, hhmm)
            if ahora >= cierre:
                sorteo.estado = EstadoSorteo.CERRADO
                auditoria.registrar(sesion, "SORTEO_CERRADO_AUTO", detalle=f"sorteo={sorteo.id} cierre={sorteo.hora_cierre or sorteo.horario}")
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
            momento = _momento_horario(sorteo, hhmm)
            if ahora < momento + timedelta(minutes=reglas.busqueda_inicio_min or 5):
                continue

            estado = _intentos.setdefault(sorteo.id, {"primero": ahora, "lecturas": []})

            numeros = obtener_resultado_oficial(sorteo.horario)

            # Log de cada intento de lectura (para debug visible).
            if numeros:
                nums_str = ",".join(f"{n:02d}" for n in numeros)
                auditoria.registrar(
                    sesion,
                    "BUSQUEDA_LECTURA",
                    detalle=f"sorteo={sorteo.id} horario={sorteo.horario} lectura={len(estado['lecturas'])+1} nums={nums_str}",
                )
                sesion.commit()
                estado["lecturas"].append(numeros)

                # TRIPLE CHECK: solo liquidar si los ultimos 3 intentos dieron los mismos numeros.
                if len(estado["lecturas"]) >= 3:
                    ultimas_tres = estado["lecturas"][-3:]
                    if ultimas_tres[0] == ultimas_tres[1] == ultimas_tres[2]:
                        sorteo.resultados = ",".join(f"{n:02d}" for n in numeros)
                        auditoria.registrar(sesion, "RESULTADO_AUTOMATICO", detalle=f"sorteo={sorteo.id} nums={sorteo.resultados} (confirmado en 3 lecturas)")
                        sesion.commit()
                        resumen = liquidar_sorteo(sorteo, sesion, reglas)
                        auditoria.registrar(sesion, "SORTEO_LIQUIDADO", detalle=str(resumen))
                        sesion.commit()
                        _actualizar_semanal(sesion, sorteo, reglas)
                        _intentos.pop(sorteo.id, None)
                    else:
                        estado["lecturas"] = [numeros]
                        auditoria.registrar(sesion, "RESULTADO_INCONSISTENTE", detalle=f"sorteo={sorteo.id}: numeros varian entre lecturas, reiniciando contador")
                        sesion.commit()
            else:
                auditoria.registrar(
                    sesion,
                    "BUSQUEDA_SIN_RESULTADO",
                    detalle=f"sorteo={sorteo.id} horario={sorteo.horario}: la pagina no devolvio numeros para este horario todavia",
                )
                sesion.commit()

                if ahora - estado["primero"] > timedelta(minutes=reglas.busqueda_duracion_min or 30):
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
