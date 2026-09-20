from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.responses import FileResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

import app.modelos  # noqa: F401  -> registra los modelos para que se creen las tablas
from app.core import security
from app.core.auth import router as router_auth
from app.core.config import Configuracion
from app.core.database import (
    SessionLocal,
    asegurar_enums,
    crear_tablas,
    migrar_modalidad,
    obtener_sesion,
    sincronizar_esquema,
)
from app.modulos_juegos import buscador, motor
from app.modulos_juegos.router_admin import router as router_juegos
from app.modulos_juegos.router_config import router as router_config
from app.modulos_roles.administrador.router import router as router_admin
from app.modulos_roles.jugador.router import router as router_jugador
from app.modulos_roles.revendedor.router import router as router_revendedor
from app.modulos_roles.vendedor.router import router as router_vendedor
from app.modelos.usuario import RolUsuario, Usuario


def crear_admin_inicial():
    """Crea el administrador principal solo si no existe ningun usuario."""
    sesion = SessionLocal()
    try:
        if sesion.query(Usuario).count() == 0:
            admin = Usuario(
                usuario=Configuracion.ADMIN_INICIAL_USUARIO,
                password_hash=security.hash_password(Configuracion.ADMIN_INICIAL_PASSWORD),
                nombre="Administrador Principal",
                rol=RolUsuario.ADMIN_PRINCIPAL,
                activo=True,
                requiere_2fa=False,
            )
            sesion.add(admin)
            sesion.commit()
    finally:
        sesion.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    crear_tablas()
    asegurar_enums()
    sincronizar_esquema()
    migrar_modalidad()
    crear_admin_inicial()
    sesion = SessionLocal()
    try:
        motor.obtener_reglas(sesion)
    finally:
        sesion.close()
    buscador.iniciar_buscador()
    yield


app = FastAPI(
    title=Configuracion.NOMBRE_APP,
    version=Configuracion.VERSION,
    lifespan=lifespan,
)
app.include_router(router_auth)
app.include_router(router_admin)
app.include_router(router_juegos)
app.include_router(router_config)
app.include_router(router_vendedor)
app.include_router(router_revendedor)
app.include_router(router_jugador)


@app.get("/")
def raiz():
    return {
        "app": Configuracion.NOMBRE_APP,
        "version": Configuracion.VERSION,
        "estado": "ok",
        "mensaje": "Fundaciones activas",
    }


@app.get("/panel")
def panel():
    """Panel visual de administracion."""
    return FileResponse("app/static/panel.html")


@app.get("/salud")
def salud():
    return {"estado": "saludable"}


@app.get("/salud/db")
def salud_db(sesion: Session = Depends(obtener_sesion)):
    """Prueba de conexion real a la base de datos."""
    try:
        sesion.execute(text("SELECT 1"))
        return {"base_de_datos": "conectada"}
    except Exception as error:
        return {"base_de_datos": "error", "detalle": str(error)}
