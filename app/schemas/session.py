from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from app.models import EntryKind, SessionStatus
from app.schemas.base import ApiModel
from app.schemas.product import ProductOut
from app.schemas.snapshot import SnapshotOut
from app.schemas.store import StoreOut
from app.services.comparison import LineStatus


class SessionCreate(ApiModel):
    store_id: int
    name: str = Field(min_length=1, max_length=120)
    baseline_snapshot_id: int | None = None


class SessionUpdate(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    status: SessionStatus | None = None
    # null explícito = comparar siempre contra el reporte más reciente
    baseline_snapshot_id: int | None = None


class SessionOut(ApiModel):
    id: int
    store: StoreOut
    name: str
    status: SessionStatus
    created_at: datetime
    closed_at: datetime | None
    baseline_snapshot_id: int | None
    baseline: SnapshotOut | None
    counted_units: int
    counted_products: int
    sold_units: int
    entries: int
    counters: list[str]
    last_activity_at: datetime | None


class ScanIn(ApiModel):
    code: str | None = Field(default=None, max_length=64)
    product_id: int | None = None
    quantity: int = Field(default=1, ge=-9999, le=9999)
    zone: str | None = Field(default=None, max_length=60)

    @model_validator(mode="after")
    def _code_or_product(self) -> "ScanIn":
        if not (self.code and self.code.strip()) and self.product_id is None:
            raise ValueError("Envía un código o un producto.")
        return self


class SaleIn(ApiModel):
    product_id: int
    quantity: int = Field(default=1, ge=1, le=999)


class EntryOut(ApiModel):
    id: int
    kind: EntryKind
    product: ProductOut
    quantity: int
    scanned_code: str | None
    user_id: int | None
    counted_by: str | None
    zone: str | None
    created_at: datetime


ScanStatus = Literal["ok", "missing", "surplus", "unexpected"]


class ScanOut(ApiModel):
    entry: EntryOut
    product: ProductOut
    counted: int
    expected: int
    in_baseline: bool
    sold: int
    status: ScanStatus


class UndoOut(ApiModel):
    product: ProductOut
    kind: EntryKind
    counted: int
    expected: int
    sold: int


class ProductStockOut(ApiModel):
    """Producto con su situación en el conteo (para registrar ventas)."""

    product: ProductOut
    in_report: bool
    reported: int
    sold: int
    expected: int
    counted: int


class ComparisonLineOut(ApiModel):
    product_id: int
    reference: str | None
    ean: str | None
    name: str
    business_unit: str | None
    size: str | None
    color_name: str | None
    reported: int
    sold: int
    expected: int
    counted: int
    difference: int
    status: LineStatus


class BucketOut(ApiModel):
    lines: int
    units: int


class ComparisonSummaryOut(ApiModel):
    expected_units: int
    counted_units: int
    matched_units: int
    accuracy: float
    progress: float
    expected_lines: int
    lines_without_ean: int
    sold_units: int
    buckets: dict[LineStatus, BucketOut]


class ComparisonOut(ApiModel):
    snapshot: SnapshotOut | None
    summary: ComparisonSummaryOut
    lines: list[ComparisonLineOut]
