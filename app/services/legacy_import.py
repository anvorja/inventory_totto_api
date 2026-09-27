"""Importa un conteo hecho con la app anterior (respaldo JSON) como un conteo actual.

Formato del respaldo: {"master": [...], "news": [...], "savedAt": ISO}. Cada ítem trae
`sku` (el EAN-13 escaneado), `bc` (la referencia Totto: los nombres venían cruzados en
esa app), `name` y `n` (unidades contadas). `news` son productos registrados a mano
durante ese conteo.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    CountEntry,
    CountSession,
    EntryKind,
    Product,
    ProductSource,
    SessionStatus,
    Store,
)
from app.services.errors import ConflictError, NotFoundError
from app.services.xlsx_parser import clean_ean, clean_reference, clean_text

LEGACY_COUNTER = "Conteo manual (app anterior)"


@dataclass
class LegacyItem:
    ean: str | None
    reference: str | None
    name: str
    quantity: int


@dataclass
class LegacyImportReport:
    saved_at: datetime
    items: int = 0
    units: int = 0
    matched_by_ean: int = 0
    ean_linked: list[str] = field(default_factory=list)  # referencias a las que se asoció EAN
    created: list[str] = field(default_factory=list)  # productos creados
    conflicts: list[str] = field(default_factory=list)  # referencia con otro EAN
    session_id: int | None = None


def read_backup(path: Path) -> tuple[datetime, list[LegacyItem]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data.get("master"), list):
        raise ConflictError("El archivo no es un respaldo de la app anterior (falta 'master').")
    saved_at = datetime.fromisoformat(str(data["savedAt"]).replace("Z", "+00:00"))
    items: dict[tuple[str | None, str | None], LegacyItem] = {}
    for raw in [*data["master"], *data.get("news", [])]:
        qty = int(raw.get("n") or 0)
        if qty <= 0:
            continue
        ean, ref = clean_ean(raw.get("sku")), clean_reference(raw.get("bc"))
        key = (ean, ref)
        if key in items:
            items[key].quantity += qty
        else:
            items[key] = LegacyItem(ean, ref, clean_text(raw.get("name")) or ref or "", qty)
    return saved_at, list(items.values())


def _resolve_product(db: Session, item: LegacyItem, report: LegacyImportReport) -> Product:
    if item.ean and (p := db.scalars(select(Product).where(Product.ean == item.ean)).first()):
        report.matched_by_ean += 1
        return p
    if item.reference and (
        p := db.scalars(select(Product).where(Product.reference == item.reference)).first()
    ):
        if p.ean is None and item.ean:
            p.ean = item.ean
            report.ean_linked.append(item.reference)
        elif item.ean and p.ean != item.ean:
            report.conflicts.append(f"{item.reference}: catálogo {p.ean}, respaldo {item.ean}")
        return p
    p = Product(ean=item.ean, reference=item.reference, name=item.name, source=ProductSource.MANUAL)
    db.add(p)
    db.flush()
    report.created.append(item.reference or item.ean or item.name)
    return p


def import_legacy_count(
    db: Session, path: Path, *, store_code: str, name: str, status: SessionStatus
) -> LegacyImportReport:
    saved_at, items = read_backup(path)
    store = db.scalars(select(Store).where(Store.code == store_code.upper())).first()
    if store is None:
        raise NotFoundError(f"No existe la tienda {store_code}.")
    if db.scalars(
        select(CountSession.id).where(CountSession.store_id == store.id, CountSession.name == name)
    ).first():
        raise ConflictError(f"Ya existe un conteo llamado '{name}': el respaldo ya se importó.")

    report = LegacyImportReport(saved_at=saved_at)
    session = CountSession(
        store_id=store.id,
        name=name,
        status=status,
        created_at=saved_at,
        closed_at=saved_at if status == SessionStatus.CLOSED else None,
    )
    db.add(session)
    db.flush()
    for item in items:
        product = _resolve_product(db, item, report)
        db.add(
            CountEntry(
                session_id=session.id,
                product_id=product.id,
                kind=EntryKind.COUNT,
                quantity=item.quantity,
                scanned_code=item.ean,
                counted_by=LEGACY_COUNTER,
                created_at=saved_at,  # conserva la hora real del conteo manual
            )
        )
        report.items += 1
        report.units += item.quantity
    db.flush()
    report.session_id = session.id
    return report
