"""Descubrimiento automatico de modalidades de sorteo.

Al importar este modulo se escanea la carpeta app/modulos_juegos/ y se registra toda
subcarpeta que contenga un plugin.py. Cada modalidad aporta, por convencion de nombre
de archivo, sus modulos: plugin.py (reglas), aprobar.py, liquidar.py, cobertura.py,
ciclo.py, validar.py. Los que no esten son opcionales.

AGREGAR UNA MODALIDAD NUEVA = crear su carpeta con sus archivos. No se modifica nada
de lo existente: el escaneo la descubre sola al proximo arranque.

Politica de errores (precaucion):
 - Si una modalidad BASE (las que ya deben funcionar: rifa, clasico) falla al cargarse,
   el arranque se FRENA con error claro: no seguimos con algo roto.
 - Si una modalidad NUEVA falla, se la EXCLUYE y se registra el motivo en errores_carga()
   (para mostrarlo como aviso); todo lo demas sigue funcionando.
"""
import importlib
import logging
from pathlib import Path

log = logging.getLogger("rifalo.modalidades")

# Modalidades que YA deben funcionar. Si una de estas falla, frenamos el arranque.
# Esta lista NO crece al agregar modalidades nuevas (es solo de seguridad).
_BASE = {"rifa", "clasico"}

_PLUGINS = {}     # clave -> instancia del plugin
_MODULOS = {}     # (clave, nombre_modulo) -> modulo
_FUNCIONES = {}   # (clave, "aprobar"|"liquidar") -> funcion
_ERRORES = {}     # clave -> motivo de exclusion


def _ruta_base() -> Path:
    return Path(__file__).resolve().parent


def _buscar_clase_plugin(mod):
    """Devuelve la clase del plugin por duck-typing (sin importar base, evita ciclos)."""
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
    """Devuelve la primera funcion del modulo que empiece con alguno de los prefijos."""
    for nombre in dir(mod):
        if nombre.startswith("_"):
            continue
        if any(nombre.startswith(p) for p in prefijos):
            obj = getattr(mod, nombre)
            if callable(obj):
                return obj
    return None


def _cargar_todo():
    global _PLUGINS, _MODULOS, _FUNCIONES, _ERRORES
    _PLUGINS, _MODULOS, _FUNCIONES, _ERRORES = {}, {}, {}, {}
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
                    pass  # modulo opcional
            fn_aprobar = _detectar_funcion(_MODULOS.get((clave, "aprobar")), ("aprobar_jugada", "aprobar")) if (clave, "aprobar") in _MODULOS else None
            fn_liquidar = _detectar_funcion(_MODULOS.get((clave, "liquidar")), ("liquidar_sorteo", "liquidar")) if (clave, "liquidar") in _MODULOS else None
            if fn_aprobar:
                _FUNCIONES[(clave, "aprobar")] = fn_aprobar
            if fn_liquidar:
                _FUNCIONES[(clave, "liquidar")] = fn_liquidar
            log.info("Modalidad descubierta: %s", clave)
        except Exception as e:
            motivo = f"{carpeta}: {e}"
            log.error("Fallo al cargar modalidad %s: %s", carpeta, e)
            if carpeta in _BASE:
                # Una modalidad base rota: frenamos el arranque para no seguir con algo caido.
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
    """Modalidades excluidas por error de carga (para mostrar como aviso)."""
    return dict(_ERRORES)


_cargar_todo()
