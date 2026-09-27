from datetime import datetime

from app.schemas.base import ApiModel
from app.schemas.store import StoreOut


class SnapshotOut(ApiModel):
    id: int
    store_id: int
    source_filename: str
    effective_at: datetime
    created_at: datetime
    line_count: int
    total_units: int


class SnapshotImportOut(ApiModel):
    snapshot: SnapshotOut
    store: StoreOut
    duplicate: bool
    new_products: int
    lines_without_ean: int


class CatalogImportOut(ApiModel):
    created: int
    updated: int
    unchanged: int
    conflicts: int
    total: int
    columns_swapped: bool


class ImportOut(ApiModel):
    kind: str
    skipped_rows: int
    snapshots: list[SnapshotImportOut] = []
    catalog: CatalogImportOut | None = None
