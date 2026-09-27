from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import User
from app.services.access import ensure_admin
from app.services.errors import PasswordChangeRequiredError, UnauthorizedError

DbSession = Annotated[Session, Depends(get_db)]

SESSION_EXPIRED = "Tu sesión expiró. Vuelve a ingresar."


def _token_from(request: Request) -> str | None:
    token = request.cookies.get(get_settings().cookie_name)
    if token:
        return token
    # Alternativa para integraciones/scripts: Authorization: Bearer <token>
    scheme, _, value = request.headers.get("Authorization", "").partition(" ")
    return value if scheme.lower() == "bearer" and value else None


def get_current_user(request: Request, db: DbSession) -> User:
    token = _token_from(request)
    payload = decode_access_token(token) if token else None
    if not payload:
        raise UnauthorizedError(SESSION_EXPIRED)
    user = db.get(User, int(payload["sub"]))
    if user is None or not user.is_active or user.token_version != payload.get("ver"):
        raise UnauthorizedError(SESSION_EXPIRED)
    return user


def get_active_user(user: Annotated[User, Depends(get_current_user)]) -> User:
    """Usuario autenticado que ya cambió su contraseña temporal."""
    if user.must_change_password:
        raise PasswordChangeRequiredError(
            "Debes cambiar tu contraseña temporal antes de continuar."
        )
    return user


def get_admin_user(user: Annotated[User, Depends(get_active_user)]) -> User:
    ensure_admin(user)
    return user


CurrentUser = Annotated[User, Depends(get_active_user)]
AdminUser = Annotated[User, Depends(get_admin_user)]
