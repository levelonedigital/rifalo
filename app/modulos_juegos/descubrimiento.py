"""Descubrimiento automatico de modalidades de sorteo.

Al importar este modulo se escanea la carpeta app/modulos_juegos/ y se registra toda
subcarpeta que contenga un plugin.py. Cada modalidad aporta, por convencion de nombre
de archivo, sus modulos: plugin.py (reglas), aprobar.py, liquidar.py, cobertura.py,
ciclo.py, validar.py. Los que no esten son opcionales.

AGREGAR UNA MODALIDAD NUEVA = crear su carpeta con sus archivos. No se modifica nada
de lo existente: el escaneo la descubre sola al proximo arranque.

Hook opcional: si algun modulo de la carpeta define la funcion alimentar_desde_diario,
se registra como hook post-liquidacion de sorteos diarios (lo usa semanal).

Politica de errores (precaucion):
 - Si una modalidad BASE (rifa, clasico) falla al cargarse, el arranque se FRENA.
 - Si una modalidad NUEVA falla, se la EXCLUYE y se registra el motivo; el resto sigue.
"""
import importlib
import logging
from pathlib import Path

log = logging.getLogger("rifalo.modalidades")

_BASE = {"rifa", "clasico"}

_PLUGINS = {}
_MODULOS = {}
_FUNCIONES = {}
_HOOKS_DIARIO = {}
_ERRORES = {}


def _ruta_base() -> Path:
    return Path(__file__).resolve().parent


def _buscar_clase_plugin(mod):
    for nombre in vars(mod):
        obj = getattr(mod, nombre)
        if (
            isinstance(obj, type)
            and getattr(obj, "clave", "")
            and hasattr(obj, "gana")
            and hasattr(obj, "calcular_premio")
        ):
            return obj
    return None


def _detectar_funcion(mod, prefijos):
    if mod is None:
        return None
    for nombre in dir(mod):
        if nombre.startswith("_"):
            continue
        if any(nombre.startswith(p) for p in prefijos):
            obj = getattr(mod, nombre)
            if callable(obj):
                return obj
    return None


def _detectar_hook_diario(modulos):
    for m in modulos:
        fn = getattr(m, "alimentar_desde_diario", None)
        if callable(fn):
            return fn
    return None


def _cargar_todo():
    global _PLUGINS, _MODULOS, _FUNCIONES, _HOOKS_DIARIO, _ERRORES
    _PLUGINS, _MODULOS, _FUNCIONES, _HOOKS_DIARIO, _ERRORES = {}, {}, {}, {}, {}
    base = _ruta_base()

    for entrada in sorted(base.iterdir()):
        if not entrada.is_dir():
            continue
        if not (entrada / "plugin.py").exists():
            continue
        carpeta = entrada.name
        try:
            plugin_mod = importlib.import_module(f"app.modulos_juegos.{carpeta}.plugin")
            clase = _buscar_clase_plugin(plugin_mod)
            if clase is None:
                raise RuntimeError("plugin.py no define una clase de modalidad valida")
            instancia = clase()
            clave = instancia.clave
            if clave != carpeta:
                raise RuntimeError(f"la clave del plugin ({clave}) no coincide con la carpeta ({carpeta})")
            _PLUGINS[clave] = instancia

            for nombre_mod in ("aprobar", "liquidar", "cobertura", "ciclo", "validar"):
                try:
                    m = importlib.import_module(f"app.modulos_juegos.{carpeta}.{nombre_mod}")
                    _MODULOS[(clave, nombre_mod)] = m
                except ModuleNotFoundError:
                    pass

            mods_cargados = [
                _MODULOS[(clave, n)]
                for n in ("aprobar", "liquidar", "cobertura", "ciclo", "validar")
                if (clave, n) in _MODULOS
            ]
            fn_aprobar = _detectar_funcion(
                _MODULOS.get((clave, "aprobar")), ("aprobar_jugada", "aprobar")
            )
            fn_liquidar = _detectar_funcion(
                _MODULOS.get((clave, "liquidar")), ("liquidar_sorteo", "liquidar")
            )
            if fn_aprobar:
                _FUNCIONES[(clave, "aprobar")] = fn_aprobar
            if fn_liquidar:
                _FUNCIONES[(clave, "liquidar")] = fn_liquidar
            hook = _detectar_hook_diario(mods_cargados)
            if hook:
                _HOOKS_DIARIO[clave] = hook
            log.info("Modalidad descubierta: %s", clave)
        except Exception as e:
            motivo = f"{carpeta}: {e}"
            log.error("Fallo al cargar modalidad %s: %s", carpeta, e)
            if carpeta in _BASE:
                raise RuntimeError(f"Modalidad base {carpeta} fallo al cargarse: {e}") from e
            _ERRORES[carpeta] = motivo
            _PLUGINS.pop(carpeta, None)


def obtener_plugin(clave: str):
    return _PLUGINS.get(clave)


def plugins() -> dict:
    return dict(_PLUGINS)


def obtener_modulo(clave: str, nombre_mod: str):
    return _MODULOS.get((clave, nombre_mod))


def obtener_aprobar(clave: str):
    return _FUNCIONES.get((clave, "aprobar"))


def obtener_liquidar(clave: str):
    return _FUNCIONES.get((clave, "liquidar"))


def hooks_post_diario():
    """Funciones alimentar_desde_diario de todas las modalidades que la definan."""
    return list(_HOOKS_DIARIO.values())


def listar_modalidades():
    salida = []
    for m in _PLUGINS.values():
        salida.append(
            {
                "clave": m.clave,
                "nombre": m.nombre,
                "resumen_reglas": m.resumen_reglas,
                "cantidad_numeros": m.cantidad_numeros,
                "permite_repetidos": m.permite_repetidos,
                "requiere_pozo": m.requiere_pozo,
                "usa_premio_fijo": m.usa_premio_fijo,
                "oculta": getattr(m, "oculta", False),
            }
        )
    return salida


def errores_carga() -> dict:
    return dict(_ERRORES)


_cargar_todo()
