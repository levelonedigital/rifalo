from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

import app.modelos  # noqa: F401  -> registra los modelos para que se creen las tablas
from app.core import security
from app.core.auth import router as router_auth
from app.core.config import Configuracion
from app.core.database import SessionLocal, crear_tablas, obtener_sesion, sincronizar_esquema
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
    # Al arrancar: crea tablas nuevas, sincroniza columnas y asegura el admin.
    crear_tablas()
    sincronizar_esquema()
    crear_admin_inicial()
    yield


app = FastAPI(
    title=Configuracion.NOMBRE_APP,
    version=Configuracion.VERSION,
    lifespan=lifespan,
)
app.include_router(router_auth)


@app.get("/")
def raiz():
    return {
        "app": Configuracion.NOMBRE_APP,
        "version": Configuracion.VERSION,
        "estado": "ok",
        "mensaje": "Fundaciones activas",
    }


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
