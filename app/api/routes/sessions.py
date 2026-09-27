import re
from datetime import datetime

from fastapi import APIRouter, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.deps import AdminUser, CurrentUser, DbSession
from app.models import CountSession, StockSnapshot, Store, User
from app.schemas.product import ProductOut
from app.schemas.session import (
    ComparisonLineOut,
    ComparisonOut,
    ComparisonSummaryOut,
    EntryOut,
    ScanIn,
    ScanOut,
    SessionCreate,
    SessionOut,
    SessionUpdate,
    UndoOut,
)
from app.schemas.snapshot import SnapshotOut
from app.schemas.store import StoreOut
from app.services import comparison, counting, export
from app.services.access import ensure_store_access

router = APIRouter(prefix="/sessions", tags=["sessions"])


def session_out(db: Session, session: CountSession) -> SessionOut:
    stats = counting.session_stats(db, session.id)
    baseline = counting.resolve_baseline(db, session)
    return SessionOut(
        id=session.id,
        store=StoreOut.model_validate(session.store),
        name=session.name,
        status=session.status,
        created_at=session.created_at,
        closed_at=session.closed_at,
        baseline_snapshot_id=session.baseline_snapshot_id,
        baseline=SnapshotOut.model_validate(baseline) if baseline else None,
        counted_units=stats.counted_units,
        counted_products=stats.counted_products,
        entries=stats.entries,
        counters=stats.counters,
        last_activity_at=stats.last_activity_at,
    )


def _snapshot_for(
    db: Session, session: CountSession, snapshot_id: int | None
) -> StockSnapshot | None:
    if snapshot_id is None:
        return counting.resolve_baseline(db, session)
    snapshot = db.get(StockSnapshot, snapshot_id)
    if snapshot is None or snapshot.store_id != session.store_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Ese reporte no es de esta tienda.")
    return snapshot


def _session_for(db: Session, user: User, session_id: int) -> CountSession:
    session = counting.get_session(db, session_id)
    ensure_store_access(user, session.store_id)
    return session


@router.post("", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
def create_session(body: SessionCreate, db: DbSession, admin: AdminUser) -> SessionOut:
    ensure_store_access(admin, body.store_id)
    if db.get(Store, body.store_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "La tienda no existe.")
    session = CountSession(
        store_id=body.store_id,
        name=body.name.strip(),
        baseline_snapshot_id=body.baseline_snapshot_id,
        created_by_id=admin.id,
    )
    db.add(session)
    db.commit()
    return session_out(db, session)


@router.get("/{session_id}", response_model=SessionOut)
def get_session(session_id: int, db: DbSession, user: CurrentUser) -> SessionOut:
    return session_out(db, _session_for(db, user, session_id))


@router.patch("/{session_id}", response_model=SessionOut)
def update_session(
    session_id: int, body: SessionUpdate, db: DbSession, admin: AdminUser
) -> SessionOut:
    session = _session_for(db, admin, session_id)
    if body.name is not None:
        session.name = body.name.strip()
    if body.status is not None:
        counting.set_status(db, session, body.status)
    if "baseline_snapshot_id" in body.model_fields_set:
        if body.baseline_snapshot_id is not None:
            _snapshot_for(db, session, body.baseline_snapshot_id)
        session.baseline_snapshot_id = body.baseline_snapshot_id
    db.commit()
    return session_out(db, session)


@router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(session_id: int, db: DbSession, admin: AdminUser) -> None:
    db.delete(_session_for(db, admin, session_id))
    db.commit()


@router.post("/{session_id}/scans", response_model=ScanOut, status_code=status.HTTP_201_CREATED)
def scan(session_id: int, body: ScanIn, db: DbSession, user: CurrentUser) -> ScanOut:
    _session_for(db, user, session_id)
    outcome = counting.record(
        db,
        session_id,
        code=body.code,
        product_id=body.product_id,
        quantity=body.quantity,
        user=user,
        zone=body.zone,
    )
    db.commit()
    return ScanOut(
        entry=EntryOut.model_validate(outcome.entry),
        product=ProductOut.model_validate(outcome.product),
        counted=outcome.counted,
        expected=outcome.expected,
        in_baseline=outcome.in_baseline,
        status=comparison.classify(outcome.expected, outcome.counted, outcome.in_baseline).value,
    )


@router.get("/{session_id}/scans", response_model=list[EntryOut])
def recent_scans(
    session_id: int, db: DbSession, user: CurrentUser, limit: int = 30
) -> list[EntryOut]:
    _session_for(db, user, session_id)
    return [
        EntryOut.model_validate(e) for e in counting.recent_entries(db, session_id, min(limit, 200))
    ]


@router.delete("/{session_id}/scans/{entry_id}", response_model=UndoOut)
def undo_scan(session_id: int, entry_id: int, db: DbSession, user: CurrentUser) -> UndoOut:
    _session_for(db, user, session_id)
    product, counted = counting.undo_entry(db, session_id, entry_id, user)
    db.commit()
    return UndoOut(product=ProductOut.model_validate(product), counted=counted)


@router.get("/{session_id}/comparison", response_model=ComparisonOut)
def get_comparison(
    session_id: int, db: DbSession, user: CurrentUser, snapshot_id: int | None = None
) -> ComparisonOut:
    session = _session_for(db, user, session_id)
    snapshot = _snapshot_for(db, session, snapshot_id)
    summary, lines = comparison.build_comparison(db, session.id, snapshot)
    return ComparisonOut(
        snapshot=SnapshotOut.model_validate(snapshot) if snapshot else None,
        summary=ComparisonSummaryOut.model_validate(summary),
        lines=[ComparisonLineOut.model_validate(line, from_attributes=True) for line in lines],
    )


@router.get("/{session_id}/export")
def export_xlsx(
    session_id: int, db: DbSession, admin: AdminUser, snapshot_id: int | None = None
) -> Response:
    session = _session_for(db, admin, session_id)
    snapshot = _snapshot_for(db, session, snapshot_id)
    summary, lines = comparison.build_comparison(db, session.id, snapshot)
    content = export.build_workbook(session, snapshot, summary, lines)
    slug = re.sub(r"[^A-Za-z0-9]+", "-", f"{session.store.code}-{session.name}").strip("-")
    filename = f"conteo-{slug}-{datetime.now():%Y%m%d-%H%M}.xlsx"
    return Response(
        content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
