from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.sql import func

from app.core.database import Base


class LogAuditoria(Base):
    """Registro de todas las acciones importantes del sistema."""
    __tablename__ = "logs_auditoria"

    id = Column(Integer, primary_key=True, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    nombre_usuario = Column(String(50), nullable=True)  # Queda guardado aunque el usuario se borre despues
    accion = Column(String(100), nullable=False)  # Ej: LOGIN_EXITOSO, JUGADA_APROBADA
    detalle = Column(String(500), nullable=True)
    fecha = Column(DateTime(timezone=True), server_default=func.now())
