from datetime import datetime

from pydantic import Field

from app.models import UserRole
from app.schemas.base import ApiModel
from app.schemas.store import StoreOut


class UserOut(ApiModel):
    id: int
    username: str
    full_name: str
    role: UserRole
    store: StoreOut | None
    is_active: bool
    must_change_password: bool
    last_login_at: datetime | None
    created_at: datetime


class LoginIn(ApiModel):
    username: str = Field(min_length=1, max_length=40)
    password: str = Field(min_length=1, max_length=200)


class ChangePasswordIn(ApiModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=1, max_length=200)


class UserCreate(ApiModel):
    username: str = Field(min_length=3, max_length=40)
    full_name: str = Field(min_length=2, max_length=80)
    role: UserRole = UserRole.ASESOR
    store_id: int | None = None


class UserUpdate(ApiModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=80)
    role: UserRole | None = None
    store_id: int | None = None
    is_active: bool | None = None


class UserWithPasswordOut(ApiModel):
    user: UserOut
    # Se muestra una sola vez al administrador para que se la entregue al usuario.
    temporary_password: str
