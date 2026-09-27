import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class ProductSource(enum.StrEnum):
    CATALOG = "catalog"  # maestro de códigos de barras (BarrcodeFQ95.xlsx)
    STOCK = "stock"  # visto por primera vez en un reporte de existencias
    MANUAL = "manual"  # registrado desde la app durante un conteo


class Product(TimestampMixin, Base):
    """Catálogo unificado.

    `reference` es el "Código Producto Largo" de Totto (modelo-temporada-color[-talla]).
    `ean` es el código de barras impreso en la etiqueta (EAN-13), lo que se escanea.
    """

    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str | None] = mapped_column(String(40), unique=True)
    ean: Mapped[str | None] = mapped_column(String(14), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    business_unit: Mapped[str | None] = mapped_column(String(60))
    size: Mapped[str | None] = mapped_column(String(20))
    color_code: Mapped[str | None] = mapped_column(String(20))
    color_name: Mapped[str | None] = mapped_column(String(80))
    source: Mapped[ProductSource] = mapped_column(
        Enum(ProductSource, name="product_source", values_callable=lambda e: [m.value for m in e])
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
