from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import AdminUser, CurrentUser, DbSession
from app.models import CountSession, StockSnapshot
from app.schemas.snapshot import SnapshotOut
from app.services.access import ensure_store_access

router = APIRouter(prefix="/snapshots", tags=["snapshots"])


@router.get("/{snapshot_id}", response_model=SnapshotOut)
def get_snapshot(snapshot_id: int, db: DbSession, user: CurrentUser) -> StockSnapshot:
    snapshot = db.get(StockSnapshot, snapshot_id)
    if snapshot is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El reporte no existe.")
    ensure_store_access(user, snapshot.store_id)
    return snapshot


@router.delete("/{snapshot_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_snapshot(snapshot_id: int, db: DbSession, admin: AdminUser) -> None:
    snapshot = db.get(StockSnapshot, snapshot_id)
    if snapshot is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "El reporte no existe.")
    ensure_store_access(admin, snapshot.store_id)
    pinned = db.scalars(
        select(CountSession.id).where(CountSession.baseline_snapshot_id == snapshot_id)
    ).first()
    if pinned:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Hay un conteo que se compara contra este reporte."
        )
    db.delete(snapshot)
    db.commit()
