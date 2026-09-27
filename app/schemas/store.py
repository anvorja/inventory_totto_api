from datetime import datetime

from app.schemas.base import ApiModel


class StoreOut(ApiModel):
    id: int
    code: str
    name: str


class StoreOverview(StoreOut):
    latest_snapshot_at: datetime | None
    open_sessions: int
