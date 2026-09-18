import enum
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum, Float, ForeignKey
from sqlalchemy.sql import func

from app.core.database import Base


class RolUsuario(str, enum.Enum):
    """Roles posibles dentro de RIFALO."""
    ADMIN_PRINCIPAL = "admin_principal"
    ADMIN = "admin"
    REVENDEDOR = "revendedor"
    JUGADOR = "jugador"


class Usuario(Base):
    """Modelo de la tabla de usuarios (admins, revendedores y jugadores)."""
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, index=True)
    usuario = Column(String(50), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    nombre = Column(String(100), nullable=False)
    telefono = Column(String(20), nullable=True)
    rol = Column(Enum(RolUsuario, name="rol_usuario"), nullable=False)
    activo = Column(Boolean, default=True)
    requiere_2fa = Column(Boolean, default=False)
    secreto_2fa = Column(String(64), nullable=True)
    creado_en = Column(DateTime(timezone=True), server_default=func.now())

    # Campos de administradores secundarios
    permisos = Column(String(500), nullable=True)  # lista separada por comas

    # Campos de revendedores
    codigo = Column(String(10), unique=True, index=True, nullable=True)
    comision_pct = Column(Float, nullable=True)
    datos_transferencia = Column(String(300), nullable=True)

    # Campo de jugadores: a que revendedor pertenece
    revendedor_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)

    def lista_permisos(self):
        """Devuelve los permisos como lista."""
        if not self.permisos:
            return []
        return [p.strip() for p in self.permisos.split(",") if p.strip()]

    def fijar_permisos(self, permisos):
        """Guarda una lista de permisos como texto."""
        self.permisos = ",".join(permisos) if permisos else None
