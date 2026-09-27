from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Product, ProductSource, StockSnapshot, StockSnapshotLine, Store
from app.services.xlsx_parser import StoreStock


def get_or_create_store(db: Session, code: str, name: str) -> Store:
    store = db.scalars(select(Store).where(Store.code == code)).first()
    if store is None:
        store = Store(code=code, name=name)
        db.add(store)
        db.flush()
    elif name and store.name != name:
        store.name = name
    return store


def latest_snapshot(db: Session, store_id: int) -> StockSnapshot | None:
    stmt = (
        select(StockSnapshot)
        .where(StockSnapshot.store_id == store_id)
        .order_by(StockSnapshot.effective_at.desc(), StockSnapshot.id.desc())
        .limit(1)
    )
    return db.scalars(stmt).first()


@dataclass
class SnapshotImportResult:
    snapshot: StockSnapshot
    duplicate: bool
    new_products: int
    lines_without_ean: int


def import_stock(
    db: Session,
    stores: list[StoreStock],
    *,
    content: bytes,
    filename: str,
    effective_at: datetime | None,
) -> list[SnapshotImportResult]:
    sha = hashlib.sha256(content).hexdigest()
    effective_at = effective_at or datetime.now(UTC)
    products = {p.reference: p for p in db.scalars(select(Product)) if p.reference}
    results: list[SnapshotImportResult] = []

    for store_stock in stores:
        store = get_or_create_store(db, store_stock.code, store_stock.name)
        existing = db.scalars(
            select(StockSnapshot).where(
                StockSnapshot.store_id == store.id, StockSnapshot.file_sha256 == sha
            )
        ).first()
        if existing:
            results.append(SnapshotImportResult(existing, True, 0, 0))
            continue

        new_products = 0
        lines_without_ean = 0
        snapshot = StockSnapshot(
            store=store,
            source_filename=filename[:255],
            file_sha256=sha,
            effective_at=effective_at,
            line_count=len(store_stock.lines),
            total_units=store_stock.total_units,
        )
        db.add(snapshot)
        for line in store_stock.lines.values():
            product = products.get(line.reference)
            if product is None:
                product = Product(
                    reference=line.reference,
                    name=line.name or line.reference,
                    source=ProductSource.STOCK,
                )
                db.add(product)
                products[line.reference] = product
                new_products += 1
            # El reporte de existencias es la fuente más fresca de atributos del producto.
            # Solo se asigna lo que cambia para no generar UPDATE innecesarios.
            for attr in ("name", "business_unit", "size", "color_code", "color_name"):
                value = getattr(line, attr)
                if value and getattr(product, attr) != value:
                    setattr(product, attr, value)
            if not product.ean:
                lines_without_ean += 1
            snapshot.lines.append(StockSnapshotLine(product=product, quantity=line.quantity))
        db.flush()
        results.append(SnapshotImportResult(snapshot, False, new_products, lines_without_ean))
    return results
