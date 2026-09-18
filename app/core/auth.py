from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core import auditoria, security
from app.core.database import obtener_sesion
from app.core.dependencias import obtener_usuario_actual
from app.modelos.usuario import RolUsuario, Usuario

router = APIRouter(prefix="/auth", tags=["auth"])


class DatosLogin(BaseModel):
    usuario: str
    password: str
    codigo_2fa: str | None = None


class DatosLoginOk(BaseModel):
    token: str
    rol: str
    nombre: str


@router.post("/login", response_model=DatosLoginOk)
def login(datos: DatosLogin, sesion: Session = Depends(obtener_sesion)):
    """Inicio de sesion con usuario, contrasenia y 2FA opcional."""
    usuario = sesion.query(Usuario).filter(Usuario.usuario == datos.usuario).first()
    if usuario is None or not security.verificar_password(datos.password, usuario.password_hash):
        auditoria.registrar(sesion, "LOGIN_FALLIDO", detalle=f"usuario intentado: {datos.usuario}")
        sesion.commit()
        raise HTTPException(status_code=401, detail="Usuario o contrasenia incorrectos")

    if not usuario.activo:
        auditoria.registrar(sesion, "LOGIN_BLOQUEADO", detalle="usuario desactivado", usuario=usuario)
        sesion.commit()
        raise HTTPException(status_code=403, detail="Usuario desactivado")

    es_admin = usuario.rol in (RolUsuario.ADMIN_PRINCIPAL, RolUsuario.ADMIN)
    if es_admin or usuario.requiere_2fa:
        if not datos.codigo_2fa:
            raise HTTPException(status_code=400, detail="Se requiere codigo 2FA")
        if not usuario.secreto_2fa or not security.verificar_2fa(usuario.secreto_2fa, datos.codigo_2fa):
            auditoria.registrar(sesion, "LOGIN_2FA_FALLIDO", usuario=usuario)
            sesion.commit()
            raise HTTPException(status_code=401, detail="Codigo 2FA incorrecto")

    token = security.crear_token(usuario.id, usuario.rol.value)
    auditoria.registrar(sesion, "LOGIN_EXITOSO", usuario=usuario)
    sesion.commit()
    return DatosLoginOk(token=token, rol=usuario.rol.value, nombre=usuario.nombre)


@router.get("/me")
def yo(usuario: Usuario = Depends(obtener_usuario_actual)):
    """Devuelve los datos del usuario autenticado."""
    return {
        "id": usuario.id,
        "usuario": usuario.usuario,
        "nombre": usuario.nombre,
        "rol": usuario.rol.value,
        "telefono": usuario.telefono,
    }
