import secrets
from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash

from app.core.config import get_settings

_hasher = PasswordHash.recommended()  # Argon2id
# Hash de referencia para igualar tiempos cuando el usuario no existe.
_DUMMY_HASH = _hasher.hash("contraseña-de-relleno")
ALGORITHM = "HS256"
MIN_PASSWORD_LENGTH = 8
# Sin caracteres ambiguos (0/O, 1/l/I): se dictan en voz alta en tienda.
_TEMP_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    if password_hash is None:
        _hasher.verify(password, _DUMMY_HASH)
        return False
    return _hasher.verify(password, password_hash)


def generate_temporary_password() -> str:
    """Ej.: 'k7m2-p9xr-4tq'. Fácil de dictar y teclear en un celular."""
    groups = ("".join(secrets.choice(_TEMP_ALPHABET) for _ in range(n)) for n in (4, 4, 3))
    return "-".join(groups)


def create_access_token(user_id: int, token_version: int) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "ver": token_version,
        "iat": now,
        "exp": now + timedelta(hours=settings.session_hours),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, get_settings().secret_key, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
