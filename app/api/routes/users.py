from fastapi import APIRouter, status
from sqlalchemy import select

from app.api.deps import AdminUser, DbSession
from app.models import User
from app.schemas.user import UserCreate, UserOut, UserUpdate, UserWithPasswordOut
from app.services import auth
from app.services.errors import ForbiddenError, NotFoundError

router = APIRouter(prefix="/users", tags=["users"])


def _get_managed_user(db: DbSession, admin: User, user_id: int) -> User:
    user = db.get(User, user_id)
    # Un administrador de tienda solo gestiona usuarios de su tienda.
    if user is None or (admin.store_id is not None and user.store_id != admin.store_id):
        raise NotFoundError("El usuario no existe.")
    return user


def _scoped_store(admin: User, store_id: int | None) -> int | None:
    if admin.store_id is None:
        return store_id
    if store_id not in (None, admin.store_id):
        raise ForbiddenError("Solo puedes asignar usuarios a tu tienda.")
    return admin.store_id


@router.get("", response_model=list[UserOut])
def list_users(db: DbSession, admin: AdminUser) -> list[User]:
    stmt = select(User).order_by(User.is_active.desc(), User.role, User.full_name)
    if admin.store_id is not None:
        stmt = stmt.where(User.store_id == admin.store_id)
    return list(db.scalars(stmt))


@router.post("", response_model=UserWithPasswordOut, status_code=status.HTTP_201_CREATED)
def create_user(body: UserCreate, db: DbSession, admin: AdminUser) -> UserWithPasswordOut:
    user, temporary = auth.create_user(
        db,
        username=body.username,
        full_name=body.full_name,
        role=body.role,
        store_id=_scoped_store(admin, body.store_id),
    )
    db.commit()
    assert temporary is not None
    return UserWithPasswordOut(user=UserOut.model_validate(user), temporary_password=temporary)


@router.patch("/{user_id}", response_model=UserOut)
def update_user(user_id: int, body: UserUpdate, db: DbSession, admin: AdminUser) -> User:
    user = _get_managed_user(db, admin, user_id)
    fields = body.model_fields_set
    store_id = _scoped_store(admin, body.store_id) if "store_id" in fields else None
    auth.update_user(
        db,
        admin,
        user,
        fields=fields,
        full_name=body.full_name,
        role=body.role,
        store_id=store_id,
        is_active=body.is_active,
    )
    db.commit()
    return user


@router.post("/{user_id}/reset-password", response_model=UserWithPasswordOut)
def reset_password(user_id: int, db: DbSession, admin: AdminUser) -> UserWithPasswordOut:
    user = _get_managed_user(db, admin, user_id)
    temporary = auth.reset_password(db, user)
    db.commit()
    return UserWithPasswordOut(user=UserOut.model_validate(user), temporary_password=temporary)
