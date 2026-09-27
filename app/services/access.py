"""Reglas de acceso por rol y tienda."""

from app.models import User
from app.services.errors import ForbiddenError, NotFoundError


def ensure_store_access(user: User, store_id: int) -> None:
    # Un usuario sin tienda asignada ve todas; con tienda, solo la suya.
    # Se responde 404 (no 403) para no revelar qué otras tiendas existen.
    if user.store_id is not None and user.store_id != store_id:
        raise NotFoundError("No encontramos ese recurso en tu tienda.")


def ensure_admin(user: User) -> None:
    if not user.is_admin:
        raise ForbiddenError("Esta acción es solo para administradores.")
