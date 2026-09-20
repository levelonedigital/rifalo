from sqlalchemy import Enum as SaEnum, create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base

from app.core.config import Configuracion

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
    sesion = SessionLocal()
    try:
        yield sesion
    finally:
        sesion.close()


def crear_tablas():
    Base.metadata.create_all(bind=motor)


def asegurar_enums():
    """Agrega valores nuevos a los tipos enum de PostgreSQL."""
    if motor.dialect.name != "postgresql":
        return
    with motor.begin() as conexion:
        for tabla in Base.metadata.sorted_tables:
            for columna in tabla.columns:
                if not isinstance(columna.type, SaEnum):
                    continue
                nombre = columna.type.name
                existentes = conexion.execute(
                    text(
                        "SELECT e.enumlabel FROM pg_enum e "
                        "JOIN pg_type t ON t.oid = e.enumtypid WHERE t.typname = :n"
                    ),
                    {"n": nombre},
                ).scalars().all()
                for valor in columna.type.enums:
                    if valor not in existentes:
                        conexion.execute(
                            text(f"ALTER TYPE {nombre} ADD VALUE IF NOT EXISTS '{valor}'")
                        )


def sincronizar_esquema():
    """Agrega columnas nuevas que falten en tablas ya existentes (solo desarrollo)."""
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


def migrar_modalidad():
    """Migracion unica: copia datos viejos a columnas nuevas y elimina las obsoletas.

    - sorteos.modulo      -> sorteos.modalidad (texto libre)
    - sorteos.fecha_sorteo -> sorteos.fecha
    - jugadas.numero       -> jugadas.numeros (texto, ya cargado por el codigo nuevo)
    """
    if motor.dialect.name != "postgresql":
        return
    inspector = inspect(motor)
    with motor.begin() as conexion:
        if inspector.has_table("sorteos"):
            columnas = {c["name"] for c in inspector.get_columns("sorteos")}
            if "modulo" in columnas and "modalidad" in columnas:
                conexion.execute(
                    text("UPDATE sorteos SET modalidad = modulo::text WHERE modalidad IS NULL")
                )
            if "modulo" in columnas:
                conexion.execute(text("ALTER TABLE sorteos DROP COLUMN modulo"))
            if "fecha_sorteo" in columnas:
                if "fecha" in columnas:
                    conexion.execute(
                        text("UPDATE sorteos SET fecha = fecha_sorteo WHERE fecha IS NULL")
                    )
                conexion.execute(text("ALTER TABLE sorteos DROP COLUMN fecha_sorteo"))
        if inspector.has_table("jugadas"):
            columnas = {c["name"] for c in inspector.get_columns("jugadas")}
            if "numero" in columnas and "numeros" in columnas:
                conexion.execute(text("ALTER TABLE jugadas DROP COLUMN numero"))


def limpiar_enums_viejos():
    """Elimina el tipo enum modulo_juego si ya no se usa."""
    if motor.dialect.name != "postgresql":
        return
    with motor.begin() as conexion:
        try:
            conexion.execute(text("DROP TYPE IF EXISTS modulo_juego"))
        except Exception:
            pass
