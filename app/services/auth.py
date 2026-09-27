from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import (
    MIN_PASSWORD_LENGTH,
    generate_temporary_password,
    hash_password,
    verify_password,
)
from app.models import Store, User, UserRole
from app.services.errors import (
    ConflictError,
    NotFoundError,
    TooManyAttemptsError,
    UnauthorizedError,
)

USERNAME_RE = re.compile(r"^[a-z0-9._-]{3,40}$")
INVALID_LOGIN = "Usuario o contraseña incorrectos."


def normalize_username(username: str) -> str:
    return username.strip().lower()


def validate_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ConflictError(f"La contraseña debe tener al menos {MIN_PASSWORD_LENGTH} caracteres.")


def authenticate(db: Session, username: str, password: str) -> User:
    settings = get_settings()
    now = datetime.now(UTC)
    user = db.scalars(select(User).where(User.username == normalize_username(username))).first()

    if user and user.locked_until and user.locked_until > now:
        minutes = max(1, round((user.locked_until - now).total_seconds() / 60))
        raise TooManyAttemptsError(
            f"Demasiados intentos fallidos. Intenta de nuevo en {minutes} min."
        )

    if not verify_password(password, user.password_hash if user else None) or user is None:
        if user is not None:
            user.failed_logins += 1
            if user.failed_logins >= settings.max_failed_logins:
                user.failed_logins = 0
                user.locked_until = now + timedelta(minutes=settings.lockout_minutes)
            db.commit()
        raise UnauthorizedError(INVALID_LOGIN)

    if not user.is_active:
        raise UnauthorizedError("Tu usuario está desactivado. Habla con el administrador.")

    user.failed_logins = 0
    user.locked_until = None
    user.last_login_at = now
    db.commit()
    return user


def change_password(db: Session, user: User, current: str, new: str) -> None:
    if not verify_password(current, user.password_hash):
        raise ConflictError("La contraseña actual no es correcta.")
    validate_password(new)
    if current == new:
        raise ConflictError("La nueva contraseña debe ser distinta a la actual.")
    user.password_hash = hash_password(new)
    user.must_change_password = False
    user.token_version += 1
    db.commit()


# ------------------------------------------------------------------ administración


def _check_store(db: Session, store_id: int | None) -> None:
    if store_id is not None and db.get(Store, store_id) is None:
        raise NotFoundError("La tienda no existe.")


def create_user(
    db: Session,
    *,
    username: str,
    full_name: str,
    role: UserRole,
    store_id: int | None,
    password: str | None = None,
) -> tuple[User, str | None]:
    """Crea un usuario. Si no se da contraseña, genera una temporal y la devuelve."""
    username = normalize_username(username)
    if not USERNAME_RE.match(username):
        raise ConflictError(
            "El usuario debe tener de 3 a 40 caracteres: letras minúsculas, números, punto, "
            "guion o guion bajo."
        )
    if db.scalars(select(User.id).where(User.username == username)).first():
        raise ConflictError("Ya existe un usuario con ese nombre.")
    _check_store(db, store_id)
    temporary = None
    if password is None:
        temporary = password = generate_temporary_password()
    else:
        validate_password(password)
    user = User(
        username=username,
        full_name=full_name.strip(),
        role=role,
        store_id=store_id,
        password_hash=hash_password(password),
        must_change_password=True,
        is_active=True,
        token_version=0,
        failed_logins=0,
    )
    db.add(user)
    db.flush()
    return user, temporary


def _active_admins(db: Session) -> int:
    return (
        db.scalar(select(func.count()).where(User.role == UserRole.ADMIN, User.is_active.is_(True)))
        or 0
    )


def update_user(
    db: Session,
    actor: User,
    user: User,
    *,
    fields: set[str],
    full_name: str | None,
    role: UserRole | None,
    store_id: int | None,
    is_active: bool | None,
) -> User:
    loses_admin = (
        user.is_admin
        and user.is_active
        and (
            ("role" in fields and role != UserRole.ADMIN)
            or ("is_active" in fields and not is_active)
        )
    )
    if loses_admin and user.id == actor.id:
        raise ConflictError(
            "No puedes quitarte el rol de administrador ni desactivarte a ti mismo."
        )
    if loses_admin and _active_admins(db) <= 1:
        raise ConflictError("Debe quedar al menos un administrador activo.")

    if "full_name" in fields and full_name:
        user.full_name = full_name.strip()
    if "role" in fields and role:
        user.role = role
    if "store_id" in fields:
        _check_store(db, store_id)
        user.store_id = store_id
    if "is_active" in fields and is_active is not None:
        if not is_active:
            user.token_version += 1  # cierra sus sesiones abiertas
        user.is_active = is_active
    db.flush()
    return user


def reset_password(db: Session, user: User) -> str:
    temporary = generate_temporary_password()
    user.password_hash = hash_password(temporary)
    user.must_change_password = True
    user.token_version += 1
    user.failed_logins = 0
    user.locked_until = None
    db.flush()
    return temporary
