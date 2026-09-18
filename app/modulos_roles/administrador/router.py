from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core import auditoria, security
from app.core.database import obtener_sesion
from app.core.dependencias import obtener_usuario_actual, requerir_permiso, requerir_rol
from app.modulos_roles.administrador import schemas
from app.modelos.auditoria import LogAuditoria
from app.modelos.usuario import RolUsuario, Usuario

router = APIRouter(prefix="/admin", tags=["admin"])

PERMISOS_POSIBLES = [
    "gestionar_revendedores",
    "configurar_sorteos",
    "cargar_resultados",
    "ver_auditoria",
]


def _admin_out(admin: Usuario) -> schemas.AdminOut:
    return schemas.AdminOut(
        id=admin.id,
        usuario=admin.usuario,
        nombre=admin.nombre,
        permisos=admin.lista_permisos(),
        activo=admin.activo,
    )


# ---------- REVENDEDORES ----------

@router.post("/revendedores", response_model=schemas.RevendedorOut)
def crear_revendedor(
    datos: schemas.RevendedorCrear,
    sesion: Session = Depends(obtener_sesion),
    admin: Usuario = Depends(requerir_permiso("gestionar_revendedores")),
):
    if sesion.query(Usuario).filter(Usuario.usuario == datos.usuario).first():
        raise HTTPException(status_code=400, detail="El nombre de usuario ya existe")
    if sesion.query(Usuario).filter(Usuario.codigo == datos.codigo.upper()).first():
        raise HTTPException(status_code=400, detail="El codigo de revendedor ya existe")
    revendedor = Usuario(
        usuario=datos.usuario,
        password_hash=security.hash_password(datos.password),
        nombre=datos.nombre,
        telefono=datos.telefono,
        rol=RolUsuario.REVENDEDOR,
        codigo=datos.codigo.upper(),
        comision_pct=datos.comision_pct,
        datos_transferencia=datos.datos_transferencia,
        activo=True,
    )
    sesion.add(revendedor)
    sesion.commit()
    sesion.refresh(revendedor)
    auditoria.registrar(
        sesion, "REVENDEDOR_CREADO", detalle=f"{revendedor.usuario} ({revendedor.codigo})", usuario=admin
    )
    sesion.commit()
    return revendedor


@router.get("/revendedores", response_model=list[schemas.RevendedorOut])
def listar_revendedores(
    sesion: Session = Depends(obtener_sesion),
    admin: Usuario = Depends(requerir_permiso("gestionar_revendedores")),
):
    return (
        sesion.query(Usuario)
        .filter(Usuario.rol == RolUsuario.REVENDEDOR)
        .order_by(Usuario.nombre)
        .all()
    )


@router.put("/revendedores/{revendedor_id}", response_model=schemas.RevendedorOut)
def editar_revendedor(
    revendedor_id: int,
    datos: schemas.RevendedorEditar,
    sesion: Session = Depends(obtener_sesion),
    admin: Usuario = Depends(requerir_permiso("gestionar_revendedores")),
):
    revendedor = sesion.get(Usuario, revendedor_id)
    if revendedor is None or revendedor.rol != RolUsuario.REVENDEDOR:
        raise HTTPException(status_code=404, detail="Revendedor no encontrado")
    for campo in ("nombre", "telefono", "codigo", "comision_pct", "datos_transferencia", "activo"):
        valor = getattr(datos, campo)
        if valor is not None:
            setattr(revendedor, campo, valor)
    sesion.commit()
    sesion.refresh(revendedor)
    auditoria.registrar(sesion, "REVENDEDOR_EDITADO", detalle=revendedor.usuario, usuario=admin)
    sesion.commit()
    return revendedor


# ---------- ADMINISTRADORES SECUNDARIOS (solo admin principal) ----------

@router.post("/admins", response_model=schemas.AdminOut)
def crear_admin(
    datos: schemas.AdminCrear,
    sesion: Session = Depends(obtener_sesion),
    admin: Usuario = Depends(requerir_rol(RolUsuario.ADMIN_PRINCIPAL)),
):
    if sesion.query(Usuario).filter(Usuario.usuario == datos.usuario).first():
        raise HTTPException(status_code=400, detail="El nombre de usuario ya existe")
    permisos_validos = [p for p in datos.permisos if p in PERMISOS_POSIBLES]
    nuevo = Usuario(
        usuario=datos.usuario,
        password_hash=security.hash_password(datos.password),
        nombre=datos.nombre,
        rol=RolUsuario.ADMIN,
        activo=True,
    )
    nuevo.fijar_permisos(permisos_validos)
    sesion.add(nuevo)
    sesion.commit()
    sesion.refresh(nuevo)
    auditoria.registrar(sesion, "ADMIN_CREADO", detalle=f"{nuevo.usuario} permisos={permisos_validos}", usuario=admin)
    sesion.commit()
    return _admin_out(nuevo)


@router.get("/admins", response_model=list[schemas.AdminOut])
def listar_admins(
    sesion: Session = Depends(obtener_sesion),
    admin: Usuario = Depends(requerir_rol(RolUsuario.ADMIN_PRINCIPAL)),
):
    admins = sesion.query(Usuario).filter(Usuario.rol == RolUsuario.ADMIN).order_by(Usuario.nombre).all()
    return [_admin_out(a) for a in admins]


@router.put("/admins/{admin_id}", response_model=schemas.AdminOut)
def editar_admin(
    admin_id: int,
    datos: schemas.AdminEditar,
    sesion: Session = Depends(obtener_sesion),
    admin: Usuario = Depends(requerir_rol(RolUsuario.ADMIN_PRINCIPAL)),
):
    objetivo = sesion.get(Usuario, admin_id)
    if objetivo is None or objetivo.rol != RolUsuario.ADMIN:
        raise HTTPException(status_code=404, detail="Admin no encontrado")
    if objetivo.id == admin.id and datos.activo is False:
        raise HTTPException(status_code=400, detail="No podés desactivarte a vos mismo")
    if datos.nombre is not None:
        objetivo.nombre = datos.nombre
    if datos.permisos is not None:
        objetivo.fijar_permisos([p for p in datos.permisos if p in PERMISOS_POSIBLES])
    if datos.activo is not None:
        objetivo.activo = datos.activo
    sesion.commit()
    auditoria.registrar(sesion, "ADMIN_EDITADO", detalle=objetivo.usuario, usuario=admin)
    sesion.commit()
    return _admin_out(objetivo)


# ---------- SEGURIDAD: 2FA y contrasena ----------

@router.get("/permisos")
def listar_permisos(admin: Usuario = Depends(obtener_usuario_actual)):
    return {"permisos": PERMISOS_POSIBLES}


@router.post("/seguridad/2fa/iniciar", response_model=schemas.DosFaIniciarOut)
def iniciar_2fa(
    sesion: Session = Depends(obtener_sesion),
    usuario: Usuario = Depends(obtener_usuario_actual),
):
    if usuario.rol not in (RolUsuario.ADMIN_PRINCIPAL, RolUsuario.ADMIN):
        raise HTTPException(status_code=403, detail="Solo administradores")
    secreto = security.nuevo_secreto_2fa()
    uri = security.uri_2fa(secreto, usuario.usuario)
    return schemas.DosFaIniciarOut(secreto=secreto, uri=uri)


@router.post("/seguridad/2fa/confirmar")
def confirmar_2fa(
    datos: schemas.DosFaConfirmar,
    sesion: Session = Depends(obtener_sesion),
    usuario: Usuario = Depends(obtener_usuario_actual),
):
    if usuario.rol not in (RolUsuario.ADMIN_PRINCIPAL, RolUsuario.ADMIN):
        raise HTTPException(status_code=403, detail="Solo administradores")
    if not security.verificar_2fa(datos.secreto, datos.codigo):
        raise HTTPException(status_code=400, detail="Codigo incorrecto, proba de nuevo")
    usuario.secreto_2fa = datos.secreto
    usuario.requiere_2fa = True
    sesion.commit()
    auditoria.registrar(sesion, "2FA_ACTIVADO", usuario=usuario)
    sesion.commit()
    return {"ok": True, "detalle": "Doble factor activado"}


@router.post("/seguridad/password")
def cambiar_password(
    datos: schemas.PasswordCambiar,
    sesion: Session = Depends(obtener_sesion),
    usuario: Usuario = Depends(obtener_usuario_actual),
):
    if not security.verificar_password(datos.actual, usuario.password_hash):
        raise HTTPException(status_code=400, detail="Contrasenia actual incorrecta")
    usuario.password_hash = security.hash_password(datos.nueva)
    sesion.commit()
    auditoria.registrar(sesion, "PASSWORD_CAMBIADO", usuario=usuario)
    sesion.commit()
    return {"ok": True, "detalle": "Contrasenia actualizada"}


# ---------- AUDITORIA ----------

@router.get("/auditoria", response_model=list[schemas.LogOut])
def ver_auditoria(
    limite: int = 100,
    sesion: Session = Depends(obtener_sesion),
    admin: Usuario = Depends(requerir_permiso("ver_auditoria")),
):
    return (
        sesion.query(LogAuditoria)
        .order_by(LogAuditoria.fecha.desc())
        .limit(limite)
        .all()
    )
