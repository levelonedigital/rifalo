from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import Configuracion
from app.core.database import crear_tablas, obtener_sesion


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Al arrancar la aplicacion, crea las tablas si no existen.
    crear_tablas()
    yield


app = FastAPI(
    title=Configuracion.NOMBRE_APP,
    version=Configuracion.VERSION,
    lifespan=lifespan,
)


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