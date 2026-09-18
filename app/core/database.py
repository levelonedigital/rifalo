from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.core.config import Configuracion

# Motor de conexion a la base de datos.
# pool_pre_ping evita errores si la conexion se corta por inactividad.
_args_extra = {}
if Configuracion.DATABASE_URL.startswith("sqlite"):
    _args_extra["check_same_thread"] = False

motor = create_engine(
    Configuracion.DATABASE_URL,
    pool_pre_ping=True,
    connect_args=_args_extra,
)

# Fabrica de sesiones: cada peticion usa una sesion y la cierra al terminar.
# Se exporta como SessionLocal para seguir la convencion de SQLAlchemy.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=motor)

# Base declarativa: de aca heredan todos los modelos de tablas.
Base = declarative_base()


def obtener_sesion():
    """Dependencia de FastAPI: entrega una sesion y la cierra al finalizar."""
    sesion = SessionLocal()
    try:
        yield sesion
    finally:
        sesion.close()


def crear_tablas():
    """Crea todas las tablas definidas en los modelos (si no existen)."""
    Base.metadata.create_all(bind=motor)
