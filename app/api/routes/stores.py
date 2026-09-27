from fastapi import APIRouter
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession
from app.api.routes.sessions import session_out
from app.models import CountSession, SessionStatus, StockSnapshot, Store
from app.schemas.session import SessionOut
from app.schemas.snapshot import SnapshotOut
from app.schemas.store import StoreOverview
from app.services.access import ensure_store_access

router = APIRouter(prefix="/stores", tags=["stores"])


@router.get("", response_model=list[StoreOverview])
def list_stores(db: DbSession, user: CurrentUser) -> list[StoreOverview]:
    latest = (
        select(StockSnapshot.store_id, func.max(StockSnapshot.effective_at).label("at"))
        .group_by(StockSnapshot.store_id)
        .subquery()
    )
    open_sessions = (
        select(CountSession.store_id, func.count().label("n"))
        .where(CountSession.status == SessionStatus.OPEN)
        .group_by(CountSession.store_id)
        .subquery()
    )
    stmt = (
        select(Store, latest.c.at, open_sessions.c.n)
        .outerjoin(latest, latest.c.store_id == Store.id)
        .outerjoin(open_sessions, open_sessions.c.store_id == Store.id)
        .order_by(Store.code)
    )
    if user.store_id is not None:
        stmt = stmt.where(Store.id == user.store_id)
    rows = db.execute(stmt).all()
    return [
        StoreOverview(
            id=s.id, code=s.code, name=s.name, latest_snapshot_at=at, open_sessions=n or 0
        )
        for s, at, n in rows
    ]


@router.get("/{store_id}/snapshots", response_model=list[SnapshotOut])
def list_snapshots(
    store_id: int, db: DbSession, user: CurrentUser, limit: int = 30
) -> list[StockSnapshot]:
    ensure_store_access(user, store_id)
    stmt = (
        select(StockSnapshot)
        .where(StockSnapshot.store_id == store_id)
        .order_by(StockSnapshot.effective_at.desc(), StockSnapshot.id.desc())
        .limit(min(limit, 100))
    )
    return list(db.scalars(stmt))


@router.get("/{store_id}/sessions", response_model=list[SessionOut])
def list_sessions(
    store_id: int, db: DbSession, user: CurrentUser, limit: int = 30
) -> list[SessionOut]:
    ensure_store_access(user, store_id)
    stmt = (
        select(CountSession)
        .where(CountSession.store_id == store_id)
        .order_by(CountSession.status, CountSession.created_at.desc())
        .limit(min(limit, 100))
    )
    return [session_out(db, s) for s in db.scalars(stmt)]
