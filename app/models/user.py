import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.store import Store


class UserRole(enum.StrEnum):
    ASESOR = "asesor"  # cuenta en piso y bodega
    ADMIN = "administrador"  # además carga Excel, gestiona conteos, exporta y administra usuarios


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(40), unique=True)
    full_name: Mapped[str] = mapped_column(String(80))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", values_callable=lambda e: [m.value for m in e])
    )
    # NULL = acceso a todas las tiendas. Con valor, solo ve y opera esa tienda.
    store_id: Mapped[int | None] = mapped_column(ForeignKey("stores.id", ondelete="RESTRICT"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Contraseñas temporales (creadas o restablecidas por un admin) obligan a cambiarla.
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=True)
    # Se incrementa al cambiar/restablecer contraseña o desactivar: invalida sesiones abiertas.
    token_version: Mapped[int] = mapped_column(Integer, default=0)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    store: Mapped[Store | None] = relationship()

    @property
    def is_admin(self) -> bool:
        return self.role == UserRole.ADMIN
