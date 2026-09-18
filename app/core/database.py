from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base

from app.core.config import Configuracion

# Motor de conexion a la base de datos.
_args_extra = {}
if Configuracion.DATABASE_URL.startswith("sqlite"):
    _args_extra["check_same_thread"] = False

motor = create_engine(
    Configuracion.DATABASE_URL,
    pool_pre_ping=True,
    connect_args=_args_extra,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=motor)

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


def sincronizar_esquema():
    """Agrega columnas nuevas que falten en tablas ya existentes.

    En desarrollo nos permite iterar sin migraciones complejas.
    Al lanzamiento oficial se hace base limpia, asi que esto es solo para iterar.
    """
    inspector = inspect(motor)
    with motor.begin() as conexion:
        for tabla in Base.metadata.sorted_tables:
            if not inspector.has_table(tabla.name):
                continue
            existentes = {c["name"] for c in inspector.get_columns(tabla.name)}
            for columna in tabla.columns:
                if columna.name in existentes:
                    continue
                tipo = columna.type.compile(motor.dialect)
                conexion.execute(
                    text(f"ALTER TABLE {tabla.name} ADD COLUMN {columna.name} {tipo}")
                )
