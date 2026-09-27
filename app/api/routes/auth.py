from typing import Annotated

from fastapi import APIRouter, Depends, Response, status

from app.api.deps import DbSession, get_current_user
from app.core.config import get_settings
from app.core.security import create_access_token
from app.models import User
from app.schemas.user import ChangePasswordIn, LoginIn, UserOut
from app.services import auth

router = APIRouter(prefix="/auth", tags=["auth"])

# Permite entrar aunque deba cambiar la contraseña (para poder cambiarla).
AnyUser = Annotated[User, Depends(get_current_user)]


def _set_session_cookie(response: Response, user: User) -> None:
    settings = get_settings()
    response.set_cookie(
        settings.cookie_name,
        create_access_token(user.id, user.token_version),
        max_age=settings.session_hours * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,  # type: ignore[arg-type]
        path="/",
    )


@router.post("/login", response_model=UserOut)
def login(body: LoginIn, response: Response, db: DbSession) -> User:
    user = auth.authenticate(db, body.username, body.password)
    _set_session_cookie(response, user)
    return user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        settings.cookie_name,
        path="/",
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,  # type: ignore[arg-type]
    )


@router.get("/me", response_model=UserOut)
def me(user: AnyUser) -> User:
    return user


@router.post("/change-password", response_model=UserOut)
def change_password(
    body: ChangePasswordIn, response: Response, user: AnyUser, db: DbSession
) -> User:
    auth.change_password(db, user, body.current_password, body.new_password)
    # token_version cambió: se emite una cookie nueva para esta sesión (las demás caducan).
    _set_session_cookie(response, user)
    return user
