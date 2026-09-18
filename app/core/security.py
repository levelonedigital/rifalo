import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone

import jwt
import pyotp

from app.core.config import Configuracion

_ALGORITMO_HASH = "sha256"
_ITERACIONES = 200_000


def hash_password(password: str) -> str:
    """Convierte una contrasenia en un codigo irreversible con sal."""
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac(_ALGORITMO_HASH, password.encode(), salt, _ITERACIONES)
    return f"pbkdf2${_ITERACIONES}${salt.hex()}${dk.hex()}"


def verificar_password(password: str, guardado: str) -> bool:
    """Compara una contrasenia escrita contra el hash guardado."""
    try:
        _, iteraciones, salt_hex, dk_hex = guardado.split("$")
        dk = hashlib.pbkdf2_hmac(
            _ALGORITMO_HASH, password.encode(), bytes.fromhex(salt_hex), int(iteraciones)
        )
        return secrets.compare_digest(dk.hex(), dk_hex)
    except Exception:
        return False


def crear_token(usuario_id: int, rol: str, horas: int = 12) -> str:
    """Token de sesion firmado con la clave secreta."""
    expira = datetime.now(timezone.utc) + timedelta(hours=horas)
    payload = {"sub": str(usuario_id), "rol": rol, "exp": expira}
    return jwt.encode(payload, Configuracion.SECRET_KEY, algorithm="HS256")


def decodificar_token(token: str):
    """Devuelve el payload del token, o None si es invalido o expiro."""
    try:
        return jwt.decode(token, Configuracion.SECRET_KEY, algorithms=["HS256"])
    except Exception:
        return None


def nuevo_secreto_2fa() -> str:
    """Genera un secreto nuevo para doble factor."""
    return pyotp.random_base32()


def uri_2fa(secreto: str, usuario: str) -> str:
    """URI para configurar Google Authenticator u otra app similar."""
    return pyotp.totp.TOTP(secreto).provisioning_uri(name=usuario, issuer_name="RIFALO")


def verificar_2fa(secreto: str, codigo: str) -> bool:
    """Valida el codigo de 6 digitos de la app autenticadora."""
    return pyotp.TOTP(secreto).verify(codigo, valid_window=1)
