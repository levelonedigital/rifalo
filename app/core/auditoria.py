from sqlalchemy.orm import Session

from app.modelos.auditoria import LogAuditoria
from app.modelos.usuario import Usuario


def registrar(sesion: Session, accion: str, detalle: str = None, usuario: Usuario = None):
    """Deja constancia en el log de auditoria. El commit lo hace quien llama."""
    log = LogAuditoria(
        usuario_id=usuario.id if usuario else None,
        nombre_usuario=usuario.usuario if usuario else None,
        accion=accion,
        detalle=detalle,
    )
    sesion.add(log)
