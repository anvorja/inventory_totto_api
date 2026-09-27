from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import Product, ProductSource
from app.services.errors import ConflictError
from app.services.xlsx_parser import CatalogLine, clean_ean, clean_reference


def find_by_code(db: Session, raw_code: str) -> Product | None:
    """Busca por EAN (lo que lee el escáner) o por referencia Totto (lo que se teclea)."""
    code = raw_code.strip()
    ean = clean_ean(code)
    if ean:
        # Un lector puede entregar UPC-A (12) o EAN-13 con/sin cero inicial.
        candidates = {ean, ean.zfill(13), ean.lstrip("0")}
        return db.scalars(select(Product).where(Product.ean.in_(candidates))).first()
    reference = clean_reference(code)
    if not reference:
        return None
    return db.scalars(select(Product).where(Product.reference == reference)).first()


def search_products(db: Session, query: str, limit: int = 20) -> list[Product]:
    q = query.strip()
    if not q:
        return []
    pattern = f"%{q}%"
    stmt = (
        select(Product)
        .where(
            or_(
                Product.name.ilike(pattern),
                Product.reference.ilike(pattern.replace(" ", "")),
                Product.ean.ilike(pattern),
            )
        )
        .order_by(Product.name, Product.reference)
        .limit(limit)
    )
    return list(db.scalars(stmt))


@dataclass
class CatalogImportStats:
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    conflicts: int = 0


def import_catalog(db: Session, lines: list[CatalogLine]) -> CatalogImportStats:
    stats = CatalogImportStats()
    products = list(db.scalars(select(Product)))
    by_ean = {p.ean: p for p in products if p.ean}
    by_ref = {p.reference: p for p in products if p.reference}

    for line in lines:
        product = by_ean.get(line.ean)
        if product is None and line.reference:
            product = by_ref.get(line.reference)

        if product is None:
            product = Product(
                ean=line.ean,
                reference=line.reference,
                name=line.name or line.reference or line.ean,
                source=ProductSource.CATALOG,
            )
            db.add(product)
            by_ean[line.ean] = product
            if line.reference:
                by_ref[line.reference] = product
            stats.created += 1
            continue

        changed = False
        if product.ean is None:
            product.ean = line.ean
            by_ean[line.ean] = product
            changed = True
        elif product.ean != line.ean:
            stats.conflicts += 1  # la referencia ya tiene otro EAN; no se sobrescribe
            continue
        if line.reference and product.reference is None and line.reference not in by_ref:
            product.reference = line.reference
            by_ref[line.reference] = product
            changed = True
        if line.name and not product.name:
            product.name = line.name
            changed = True
        if changed:
            stats.updated += 1
        else:
            stats.unchanged += 1

    db.flush()
    return stats


def register_product(
    db: Session,
    *,
    ean: str | None,
    reference: str | None,
    name: str | None,
) -> Product:
    """Registra un código desconocido encontrado durante el conteo.

    Si la referencia ya existe (típico: está en existencias pero no en el maestro de códigos),
    se le asocia el EAN en vez de crear un producto duplicado.
    """
    ean = clean_ean(ean) if ean else None
    reference = clean_reference(reference) if reference else None
    if not ean and not reference:
        raise ConflictError("Indica el código de barras o la referencia del producto.")

    if ean and (existing := db.scalars(select(Product).where(Product.ean == ean)).first()):
        raise ConflictError("Ese código de barras ya está registrado.", product_id=existing.id)

    if reference and (
        product := db.scalars(select(Product).where(Product.reference == reference)).first()
    ):
        if product.ean and ean and product.ean != ean:
            raise ConflictError(
                f"La referencia {reference} ya tiene otro código de barras ({product.ean}).",
                product_id=product.id,
            )
        product.ean = product.ean or ean
        if name and not product.name:
            product.name = name
        db.flush()
        return product

    if not name:
        raise ConflictError("Escribe el nombre del producto para registrarlo.")
    product = Product(ean=ean, reference=reference, name=name.strip(), source=ProductSource.MANUAL)
    db.add(product)
    db.flush()
    return product
