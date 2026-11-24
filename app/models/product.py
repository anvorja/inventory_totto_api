import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, false, func
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
    # True cuando un administrador corrigió el nombre: las cargas de Excel ya no lo sobrescriben.
    name_locked: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    # Último nombre que trajo el Excel ("el nombre del sistema"). Permite comparar con el
    # nombre corregido en la app y avisar cuando difieren.
    source_name: Mapped[str | None] = mapped_column(String(200))
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


class BarcodeChange(TimestampMixin, Base):
    """Historial de correcciones de código de barras hechas desde la app.

    Guarda quién, cuándo y de qué a qué. Las lecturas guardan `product_id`, así que corregir
    un EAN no altera conteos ya hechos; el historial permite rastrear y revertir una
    corrección equivocada.
    """

    __tablename__ = "barcode_changes"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    old_ean: Mapped[str | None] = mapped_column(String(14))
    new_ean: Mapped[str] = mapped_column(String(14))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    # Nombre congelado: se conserva aunque el usuario se renombre o se elimine.
    changed_by: Mapped[str] = mapped_column(String(80))


class ProductNameChange(TimestampMixin, Base):
    """Historial de nombres corregidos por un administrador (quién, cuándo, de qué a qué)."""

    __tablename__ = "product_name_changes"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    old_name: Mapped[str] = mapped_column(String(200))
    new_name: Mapped[str] = mapped_column(String(200))
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    changed_by: Mapped[str] = mapped_column(String(80))
