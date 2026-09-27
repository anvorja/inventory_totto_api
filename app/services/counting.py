from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models import (
    CountEntry,
    CountSession,
    EntryKind,
    Product,
    SessionStatus,
    StockSnapshot,
    User,
)
from app.services.catalog import find_by_code
from app.services.errors import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ProductNotFoundError,
    SessionClosedError,
)
from app.services.reconcile import ProductState, load_states
from app.services.snapshots import latest_snapshot


def get_session(db: Session, session_id: int) -> CountSession:
    session = db.get(CountSession, session_id)
    if session is None:
        raise NotFoundError("El conteo no existe.")
    return session


def resolve_baseline(db: Session, session: CountSession) -> StockSnapshot | None:
    if session.baseline_snapshot_id:
        return db.get(StockSnapshot, session.baseline_snapshot_id)
    return latest_snapshot(db, session.store_id)


def counted_total(db: Session, session_id: int, product_id: int) -> int:
    """Unidades leídas (solo lecturas de conteo, sin descontar ventas)."""
    stmt = select(func.coalesce(func.sum(CountEntry.quantity), 0)).where(
        CountEntry.session_id == session_id,
        CountEntry.product_id == product_id,
        CountEntry.kind == EntryKind.COUNT,
    )
    return int(db.scalar(stmt) or 0)


@dataclass
class ScanOutcome:
    entry: CountEntry
    product: Product
    counted: int  # contado que sigue en tienda (descontando ventas posteriores)
    expected: int  # esperado ahora (descontando ventas posteriores al reporte)
    in_baseline: bool
    sold: int


def product_state(db: Session, session: CountSession, product_id: int) -> ProductState:
    return load_states(db, session.id, resolve_baseline(db, session), [product_id])[product_id]


def _outcome(
    db: Session, session: CountSession, entry: CountEntry, product: Product
) -> ScanOutcome:
    state = product_state(db, session, product.id)
    return ScanOutcome(
        entry=entry,
        product=product,
        counted=state.counted,
        expected=state.expected,
        in_baseline=state.in_report,
        sold=state.sold,
    )


def _open_session(db: Session, session_id: int) -> CountSession:
    session = get_session(db, session_id)
    if session.status != SessionStatus.OPEN:
        raise SessionClosedError("Este conteo está cerrado. Reábrelo para seguir contando.")
    return session


def record(
    db: Session,
    session_id: int,
    *,
    code: str | None,
    product_id: int | None,
    quantity: int,
    user: User,
    zone: str | None,
) -> ScanOutcome:
    session = _open_session(db, session_id)
    if quantity == 0:
        raise ConflictError("La cantidad no puede ser cero.")

    product = db.get(Product, product_id) if product_id else None
    if product is None and code:
        product = find_by_code(db, code)
    if product is None:
        raise ProductNotFoundError(
            "Este código no está en el catálogo.", scanned_code=(code or "").strip()
        )

    # Bloquea la fila de la sesión para que dos correcciones simultáneas no dejen negativos.
    db.execute(select(CountSession.id).where(CountSession.id == session.id).with_for_update())
    current = counted_total(db, session.id, product.id)
    if current + quantity < 0:
        raise ConflictError(
            f"No puedes restar {abs(quantity)}: solo hay {current} contadas.", counted=current
        )

    entry = CountEntry(
        session_id=session.id,
        product_id=product.id,
        quantity=quantity,
        scanned_code=code.strip()[:40] if code else None,
        user_id=user.id,
        counted_by=user.full_name[:80],
        zone=(zone or "").strip()[:60] or None,
    )
    db.add(entry)
    db.flush()
    return _outcome(db, session, entry, product)


def record_sale(
    db: Session, session_id: int, *, product_id: int, quantity: int, user: User
) -> ScanOutcome:
    """Registra unidades vendidas mientras el conteo está en curso."""
    session = _open_session(db, session_id)
    if quantity < 1:
        raise ConflictError("La cantidad vendida debe ser al menos 1.")
    product = db.get(Product, product_id)
    if product is None:
        raise NotFoundError("El producto no existe.")
    entry = CountEntry(
        session_id=session.id,
        product_id=product.id,
        kind=EntryKind.SALE,
        quantity=quantity,
        user_id=user.id,
        counted_by=user.full_name[:80],
    )
    db.add(entry)
    db.flush()
    return _outcome(db, session, entry, product)


def undo_entry(
    db: Session, session_id: int, entry_id: int, user: User
) -> tuple[Product, EntryKind, ProductState]:
    """Deshace una lectura o una venta. Devuelve el producto y su estado resultante."""
    session = _open_session(db, session_id)
    entry = db.get(CountEntry, entry_id)
    if entry is None or entry.session_id != session_id:
        raise NotFoundError("Ese registro ya no existe.")
    if not user.is_admin and entry.user_id != user.id:
        raise ForbiddenError("Solo puedes deshacer tus propios registros.")
    product, kind = entry.product, entry.kind
    if kind == EntryKind.COUNT:
        current = counted_total(db, session_id, product.id)
        if current - entry.quantity < 0:
            raise ConflictError("No se puede deshacer: el total quedaría negativo.")
    db.delete(entry)
    db.flush()
    return product, kind, product_state(db, session, product.id)


def recent_entries(db: Session, session_id: int, limit: int = 30) -> list[CountEntry]:
    stmt = (
        select(CountEntry)
        .options(joinedload(CountEntry.product))
        .where(CountEntry.session_id == session_id)
        .order_by(CountEntry.id.desc())
        .limit(limit)
    )
    return list(db.scalars(stmt))


@dataclass
class SessionStats:
    counted_units: int  # unidades leídas al contar
    counted_products: int
    sold_units: int  # unidades vendidas registradas durante el conteo
    entries: int
    counters: list[str]
    last_activity_at: datetime | None


def session_stats(db: Session, session_id: int) -> SessionStats:
    per_product = (
        select(CountEntry.product_id, func.sum(CountEntry.quantity).label("n"))
        .where(CountEntry.session_id == session_id, CountEntry.kind == EntryKind.COUNT)
        .group_by(CountEntry.product_id)
        .subquery()
    )
    units, products = db.execute(
        select(func.coalesce(func.sum(per_product.c.n), 0), func.count())
        .select_from(per_product)
        .where(per_product.c.n > 0)
    ).one()
    sold = db.scalar(
        select(func.coalesce(func.sum(CountEntry.quantity), 0)).where(
            CountEntry.session_id == session_id, CountEntry.kind == EntryKind.SALE
        )
    )
    entries, last = db.execute(
        select(func.count(), func.max(CountEntry.created_at)).where(
            CountEntry.session_id == session_id
        )
    ).one()
    counters = db.scalars(
        select(CountEntry.counted_by)
        .where(CountEntry.session_id == session_id, CountEntry.counted_by.is_not(None))
        .distinct()
    ).all()
    return SessionStats(
        int(units), int(products), int(sold or 0), int(entries), sorted(counters), last
    )


def set_status(db: Session, session: CountSession, status: SessionStatus) -> None:
    session.status = status
    session.closed_at = datetime.now(UTC) if status == SessionStatus.CLOSED else None
