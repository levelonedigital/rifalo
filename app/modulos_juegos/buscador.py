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

# Mapeo de horarios del sistema a los "tipo" de la API oficial de la Caja.
TIPOS_QUINIELA = {
    "matutina": 1,
    "vespertina": 2,
    "siesta": 3,
    "tarde": 4,
    "nocturna": 5,
}

_URL_API = Configuracion.URL_QUINIELA.rstrip("/") + "/api/"


def _zona():
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


def _inicio_min(sorteo, reglas):
    return sorteo.busqueda_inicio_min if sorteo.busqueda_inicio_min is not None else (reglas.busqueda_inicio_min or 35)


def _intervalo_min(sorteo, reglas):
    return sorteo.busqueda_intervalo_min if sorteo.busqueda_intervalo_min is not None else (reglas.busqueda_intervalo_min or 2)


def _duracion_min(sorteo, reglas):
    return sorteo.busqueda_duracion_min if sorteo.busqueda_duracion_min is not None else (reglas.busqueda_duracion_min or 30)


def obtener_resultado_oficial(nombre_horario: str, fecha: datetime):
    """Lee los 20 numeros del horario en la fecha dada desde la API oficial de la Caja.

    Paso 1: /api/extracto/?fecha_sorteo=AAAA-MM-DD  -> lista los sorteos del dia.
    Paso 2: /api/extracto-registro/?id=<id>          -> los 20 numeros de ese sorteo.
    Devuelve la lista de 20 numeros (ultimos 2 digitos) ordenada por posicion, o None.
    """
    tipo = TIPOS_QUINIELA.get(nombre_horario)
    if tipo is None:
        return None
    dia = fecha.strftime("%Y-%m-%d")
    cabeceras = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"}
    try:
        r1 = requests.get(_URL_API + "extracto/", params={"fecha_sorteo": dia}, timeout=10, headers=cabeceras)
        r1.raise_for_status()
        extractos = r1.json()
        id_extracto = None
        for ex in extractos:
            if ex.get("tipo") == tipo and ex.get("fecha_sorteo") == dia:
                id_extracto = ex.get("id")
                break
        if id_extracto is None:
            return None

        r2 = requests.get(_URL_API + "extracto-registro/", params={"id": id_extracto}, timeout=10, headers=cabeceras)
        r2.raise_for_status()
        registros = r2.json()
        if not registros or len(registros) < 20:
            return None
        registros = sorted(registros, key=lambda x: x.get("posicion", 0))
        nums = [int(x.get("numero", 0)) % 100 for x in registros[:20]]
        if len(nums) < 20:
            return None
        return nums
    except Exception:
        return None


def costo_a_cubrir(sorteo: Sorteo) -> float:
    """Costo de referencia: minimo explicito, premio fijo (rifa) o pozo base.

    En vacantes (solo_participantes sin pozo base) no hay costo que cubrir:
    el pozo ya arranca con el monto retenido del sorteo anterior.
    """
    if sorteo.minimo_cubrir is not None:
        return sorteo.minimo_cubrir
    if sorteo.modalidad == "rifa":
        return sorteo.premio_fijo or 0.0
    if sorteo.solo_participantes and (sorteo.pozo_base or 0.0) == 0.0:
        return 0.0
    return sorteo.pozo_inicial or 0.0


def pozo_cubierto_total(sorteo: Sorteo) -> float:
    """Acumulado de sobrantes destinados al pozo (cubrir base + extra)."""
    return (sorteo.pozo_cubierto or 0.0) + (sorteo.pozo_extra or 0.0)


def estado_busquedas():
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


def chequeo_costo(sesion, reglas, ahora: datetime):
    """A 30 min del horario oficial, avisa al admin si el acumulado de sobrantes no cubre el costo."""
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
            if pozo_cubierto_total(sorteo) < costo:
                aviso = Aviso(
                    texto=(
                        f"ADMIN: sorteo #{sorteo.id} ({sorteo.modalidad} {sorteo.horario}) no cubre el costo: "
                        f"pozo cubierto ${pozo_cubierto_total(sorteo):.2f} de ${costo:.2f}. Decidi si reprogramas el horario."
                    ),
                    destino="admin",
                )
                sesion.add(aviso)
                sorteo.aviso_costo_enviado = True
                sesion.commit()


def _actualizar_semanal(sesion, sorteo_dia: Sorteo, reglas):
    """Alimenta al semanal abierto cuyo horario coincida y cuyo rango de dias incluya
    el dia del sorteo diario. Cada semanal usa SU PROPIA configuracion de dias."""
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


def ciclo():
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
            inicio = _inicio_min(sorteo, reglas)
            intervalo = _intervalo_min(sorteo, reglas)
            duracion = _duracion_min(sorteo, reglas)
            # Empieza a buscar recien pasado el inicio configurado para ESTE sorteo.
            if ahora < momento + timedelta(minutes=inicio):
                continue

            estado = _intentos.setdefault(sorteo.id, {"primero": ahora, "lecturas": [], "ultimo_ts": None})

            # Respeta el intervalo de reintento propio de este sorteo.
            ultimo_ts = estado.get("ultimo_ts")
            if ultimo_ts is not None and (ahora - ultimo_ts) < timedelta(minutes=intervalo):
                continue

            numeros = obtener_resultado_oficial(sorteo.horario, sorteo.fecha)
            estado["ultimo_ts"] = ahora

            if numeros:
                nums_str = ",".join(f"{n:02d}" for n in numeros)
                auditoria.registrar(
                    sesion,
                    "BUSQUEDA_LECTURA",
                    detalle=f"sorteo={sorteo.id} horario={sorteo.horario} lectura={len(estado['lecturas'])+1} nums={nums_str}",
                )
                sesion.commit()
                estado["lecturas"].append(numeros)

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
                    detalle=f"sorteo={sorteo.id} horario={sorteo.horario}: la API no devolvio numeros para este horario todavia",
                )
                sesion.commit()

                if ahora - estado["primero"] > timedelta(minutes=duracion):
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
