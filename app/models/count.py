import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.product import Product
from app.models.snapshot import StockSnapshot
from app.models.store import Store


class SessionStatus(enum.StrEnum):
    OPEN = "open"
    CLOSED = "closed"


class CountSession(TimestampMixin, Base):
    """Una jornada de conteo físico en una tienda. Varias personas pueden contar a la vez."""

    __tablename__ = "count_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    status: Mapped[SessionStatus] = mapped_column(
        Enum(SessionStatus, name="session_status", values_callable=lambda e: [m.value for m in e]),
        default=SessionStatus.OPEN,
    )
    # Reporte de existencias contra el que se compara. Si es NULL se usa el más reciente.
    baseline_snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("stock_snapshots.id", ondelete="SET NULL")
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    store: Mapped[Store] = relationship()
    baseline_snapshot: Mapped[StockSnapshot | None] = relationship()


class CountEntry(TimestampMixin, Base):
    """Evento de conteo (append-only). El total de un producto es la suma de sus entradas.

    Guardar eventos en lugar de un contador permite que varios celulares cuenten en paralelo
    sin pisarse, deshacer lecturas puntuales y auditar quién contó qué.
    """

    __tablename__ = "count_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("count_sessions.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), index=True
    )
    quantity: Mapped[int] = mapped_column(Integer)  # positivo al contar, negativo al corregir
    scanned_code: Mapped[str | None] = mapped_column(String(40))
    # Quién contó: FK al usuario + nombre congelado (se conserva si el usuario se renombra).
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    counted_by: Mapped[str | None] = mapped_column(String(80))
    zone: Mapped[str | None] = mapped_column(String(60))

    product: Mapped[Product] = relationship()
