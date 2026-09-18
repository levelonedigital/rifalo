from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core.database import obtener_sesion
from app.core.security import decodificar_token
from app.modelos.usuario import RolUsuario, Usuario

esquema_bearer = HTTPBearer()


def obtener_usuario_actual(
    credenciales: HTTPAuthorizationCredentials = Depends(esquema_bearer),
    sesion: Session = Depends(obtener_sesion),
) -> Usuario:
    """Valida el token de la sesion y devuelve el usuario."""
    payload = decodificar_token(credenciales.credentials)
    if payload is None:
        raise HTTPException(status_code=401, detail="Sesion invalida o expirada")
    usuario = sesion.get(Usuario, int(payload["sub"]))
    if usuario is None or not usuario.activo:
        raise HTTPException(status_code=401, detail="Usuario inexistente o desactivado")
    return usuario


def requerir_rol(*roles: RolUsuario):
    """Fabrica de dependencias: restringe una ruta a ciertos roles."""
    def dependencia(usuario: Usuario = Depends(obtener_usuario_actual)) -> Usuario:
        if usuario.rol not in roles:
            raise HTTPException(status_code=403, detail="Permisos insuficientes")
        return usuario
    return dependencia


def requerir_permiso(permiso: str):
    """Restringe una ruta a un permiso concreto. El admin principal siempre puede."""
    def dependencia(usuario: Usuario = Depends(obtener_usuario_actual)) -> Usuario:
        if usuario.rol == RolUsuario.ADMIN_PRINCIPAL:
            return usuario
        if usuario.rol != RolUsuario.ADMIN:
            raise HTTPException(status_code=403, detail="Permisos insuficientes")
        if permiso not in usuario.lista_permisos():
            raise HTTPException(status_code=403, detail=f"Permiso requerido: {permiso}")
        return usuario
    return dependencia
