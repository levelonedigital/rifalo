from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
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


class RegistroJugador(BaseModel):
    usuario: str
    password: str
    nombre: str
    telefono: str = Field(min_length=5)
    codigo_vendedor: str
    datos_cobro: str = Field(min_length=1)
    cobro_transferencia: bool = True


@router.post("/login", response_model=DatosLoginOk)
def login(datos: DatosLogin, sesion: Session = Depends(obtener_sesion)):
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
    necesita_2fa = (es_admin or usuario.requiere_2fa) and usuario.secreto_2fa
    if necesita_2fa:
        if not datos.codigo_2fa:
            raise HTTPException(status_code=400, detail="Se requiere codigo 2FA")
        if not security.verificar_2fa(usuario.secreto_2fa, datos.codigo_2fa):
            auditoria.registrar(sesion, "LOGIN_2FA_FALLIDO", usuario=usuario)
            sesion.commit()
            raise HTTPException(status_code=401, detail="Codigo 2FA incorrecto")

    token = security.crear_token(usuario.id, usuario.rol.value)
    auditoria.registrar(sesion, "LOGIN_EXITOSO", usuario=usuario)
    sesion.commit()
    return DatosLoginOk(token=token, rol=usuario.rol.value, nombre=usuario.nombre)


@router.post("/registro-jugador")
def registro_jugador(datos: RegistroJugador, sesion: Session = Depends(obtener_sesion)):
    """Un jugador se registra con el codigo de su vendedor o de un revendedor."""
    codigo = datos.codigo_vendedor.upper()
    vendedor = (
        sesion.query(Usuario)
        .filter(Usuario.codigo == codigo, Usuario.rol == RolUsuario.VENDEDOR)
        .first()
    )
    revendedor = None
    if vendedor is None or not vendedor.activo:
        revendedor = (
            sesion.query(Usuario)
            .filter(Usuario.codigo == codigo, Usuario.rol == RolUsuario.REVENDEDOR)
            .first()
        )
        if revendedor is None or not revendedor.activo or revendedor.padre_id is None:
            raise HTTPException(status_code=400, detail="Codigo de vendedor invalido")
        vendedor = sesion.get(Usuario, revendedor.padre_id)
        if vendedor is None or not vendedor.activo:
            raise HTTPException(status_code=400, detail="Codigo invalido: el vendedor duenio del revendedor no esta activo")
    if sesion.query(Usuario).filter(Usuario.usuario == datos.usuario).first():
        raise HTTPException(status_code=400, detail="El nombre de usuario ya existe")
    jugador = Usuario(
        usuario=datos.usuario,
        password_hash=security.hash_password(datos.password),
        nombre=datos.nombre,
        telefono=datos.telefono,
        rol=RolUsuario.JUGADOR,
        padre_id=vendedor.id,
        revendedor_padre_id=revendedor.id if revendedor else None,
        activo=True,
        datos_cobro=datos.datos_cobro,
        cobro_transferencia=datos.cobro_transferencia,
    )
    sesion.add(jugador)
    sesion.commit()
    via = f"revendedor={revendedor.usuario}" if revendedor else "vendedor directo"
    auditoria.registrar(
        sesion,
        "REGISTRO_JUGADOR",
        detalle=f"jugador={jugador.usuario} vendedor={vendedor.usuario} {via} cobro={jugador.datos_cobro}",
        usuario=vendedor,
    )
    sesion.commit()
    quien = revendedor.nombre if revendedor else vendedor.nombre
    return {"ok": True, "detalle": f"Jugador registrado con {quien}"}


@router.get("/me")
def yo(usuario: Usuario = Depends(obtener_usuario_actual)):
    return {
        "id": usuario.id,
        "usuario": usuario.usuario,
        "nombre": usuario.nombre,
        "rol": usuario.rol.value,
        "telefono": usuario.telefono,
        "codigo": usuario.codigo,
        "comision_pct": usuario.comision_pct,
        "datos_cobro": usuario.datos_cobro,
        "cobro_transferencia": usuario.cobro_transferencia,
    }
