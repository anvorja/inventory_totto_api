from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Store(TimestampMixin, Base):
    """Punto de venta. Se crea automáticamente al importar un reporte de existencias."""

    __tablename__ = "stores"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)  # p. ej. "FQ95"
    name: Mapped[str] = mapped_column(String(120))  # p. ej. "TOTTO VILLA GORGONA"
