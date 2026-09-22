import enum
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum, Float, ForeignKey
from sqlalchemy.sql import func

from app.core.database import Base


class RolUsuario(str, enum.Enum):
    """Jerarquia: Admin -> Vendedor -> Revendedor. Jugador se registra con codigo de vendedor o revendedor."""
    ADMIN_PRINCIPAL = "admin_principal"
    ADMIN = "admin"
    VENDEDOR = "vendedor"
    REVENDEDOR = "revendedor"
    JUGADOR = "jugador"


class Usuario(Base):
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

    # Admins secundarios
    permisos = Column(String(500), nullable=True)

    # Vendedores y revendedores
    codigo = Column(String(10), unique=True, index=True, nullable=True)
    comision_pct = Column(Float, nullable=True)
    datos_transferencia = Column(String(300), nullable=True)

    # Jugadores: datos para pagarles los premios
    datos_cobro = Column(String(200), nullable=True)      # alias o CBU del jugador
    cobro_transferencia = Column(Boolean, default=False)  # quiere cobrar sus premios por transferencia

    # Padre en la jerarquia:
    #  - REVENDEDOR: su vendedor duenio
    #  - JUGADOR: el vendedor duenio de la linea (siempre)
    padre_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    # JUGADOR registrado por un revendedor: ese revendedor (para comisiones y gestion)
    revendedor_padre_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)

    def lista_permisos(self):
        if not self.permisos:
            return []
        return [p.strip() for p in self.permisos.split(",") if p.strip()]

    def fijar_permisos(self, permisos):
        self.permisos = ",".join(permisos) if permisos else None
