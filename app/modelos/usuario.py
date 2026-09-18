import enum
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum
from sqlalchemy.sql import func

from app.core.database import Base


class RolUsuario(str, enum.Enum):
    """Roles posibles dentro de RIFALO."""
    ADMIN_PRINCIPAL = "admin_principal"
    ADMIN = "admin"
    REVENDEDOR = "revendedor"
    JUGADOR = "jugador"


class Usuario(Base):
    """Modelo de la tabla de usuarios."""
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, index=True)
    usuario = Column(String(50), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    nombre = Column(String(100), nullable=False)
    telefono = Column(String(20), nullable=True)
    rol = Column(Enum(RolUsuario, name="rol_usuario"), nullable=False)
    activo = Column(Boolean, default=True)
    requiere_2fa = Column(Boolean, default=False)  # Solo para administradores
    secreto_2fa = Column(String(64), nullable=True)  # Clave TOTP del autenticador
    creado_en = Column(DateTime(timezone=True), server_default=func.now())
