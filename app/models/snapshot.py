from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.product import Product
from app.models.store import Store


class StockSnapshot(TimestampMixin, Base):
    """Una carga del reporte de existencias ("lo que debería haber") para una tienda.

    El reporte se actualiza varias veces al día, por eso cada carga es una versión nueva
    y los conteos pueden compararse contra cualquiera de ellas.
    """

    __tablename__ = "stock_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id", ondelete="CASCADE"), index=True)
    source_filename: Mapped[str] = mapped_column(String(255))
    file_sha256: Mapped[str] = mapped_column(String(64))
    # Momento al que corresponden las existencias (lo indica quien sube el archivo;
    # por defecto, la hora de carga).
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    line_count: Mapped[int] = mapped_column(Integer)
    total_units: Mapped[int] = mapped_column(Integer)

    store: Mapped[Store] = relationship()
    lines: Mapped[list["StockSnapshotLine"]] = relationship(
        back_populates="snapshot", cascade="all, delete-orphan", passive_deletes=True
    )


class StockSnapshotLine(Base):
    __tablename__ = "stock_snapshot_lines"
    __table_args__ = (UniqueConstraint("snapshot_id", "product_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("stock_snapshots.id", ondelete="CASCADE"), index=True
    )
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"))
    quantity: Mapped[int] = mapped_column(Integer)

    snapshot: Mapped[StockSnapshot] = relationship(back_populates="lines")
    product: Mapped[Product] = relationship()
