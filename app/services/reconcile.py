"""Conciliación de lecturas y ventas registradas durante un conteo.

La tienda sigue vendiendo mientras se cuenta y el reporte de existencias se actualiza
tarde. Por eso, cada venta registrada en la app se descuenta así:

* Si ocurrió **después de la hora del reporte**, el reporte aún no la conoce: se resta de
  lo esperado. Si ocurrió antes, el reporte ya la incluye y no se resta (así subir un
  Excel nuevo es opcional y nunca descuenta dos veces).
* Si el producto **ya tenía unidades contadas** cuando se vendió, la unidad salió después
  de contarla: se resta también de lo contado. Si aún no se había contado, ya no estaba
  al contar y no hay nada que restar.

Cuando no se puede saber cuál unidad exacta se vendió (p. ej. se contó una de tres), se
asume que fue una de las ya contadas.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CountEntry, EntryKind, StockSnapshot
from app.models import StockSnapshotLine as Line


@dataclass(frozen=True)
class EntryEvent:
    at: datetime
    order: int  # desempate estable (id de la entrada)
    kind: EntryKind
    quantity: int


@dataclass(frozen=True)
class ProductState:
    reported: int  # lo que dice el reporte de existencias
    in_report: bool
    sold: int  # ventas registradas después de la hora del reporte
    counted_raw: int  # suma de lecturas (sin descontar ventas)
    sold_after_counting: int  # unidades vendidas que ya habían sido contadas

    @property
    def expected(self) -> int:
        """Lo que debería haber ahora en tienda."""
        return max(self.reported - self.sold, 0)

    @property
    def counted(self) -> int:
        """Lo contado que sigue en tienda."""
        return max(self.counted_raw - self.sold_after_counting, 0)


def _aware(value: datetime) -> datetime:
    # Postgres entrega fechas con zona; SQLite (pruebas) sin ella: se asumen en UTC.
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def reconcile(
    events: Iterable[EntryEvent],
    *,
    reported: int,
    in_report: bool,
    report_at: datetime | None,
) -> ProductState:
    counted = 0  # lecturas acumuladas hasta el momento de cada evento
    taken = 0  # unidades contadas que luego se vendieron
    sold = 0
    report_at = _aware(report_at) if report_at else None
    for event in sorted(events, key=lambda e: (_aware(e.at), e.order)):
        if event.kind == EntryKind.COUNT:
            counted += event.quantity
            continue
        available = max(counted - taken, 0)
        taken += min(event.quantity, available)
        if report_at is None or _aware(event.at) > report_at:
            sold += event.quantity
    return ProductState(
        reported=reported,
        in_report=in_report,
        sold=sold,
        counted_raw=counted,
        sold_after_counting=taken,
    )


def load_states(
    db: Session,
    session_id: int,
    snapshot: StockSnapshot | None,
    product_ids: Iterable[int] | None = None,
) -> dict[int, ProductState]:
    """Estado conciliado por producto. Sin `product_ids`: todos los del reporte y conteo."""
    ids = set(product_ids) if product_ids is not None else None

    entry_stmt = select(
        CountEntry.id,
        CountEntry.product_id,
        CountEntry.kind,
        CountEntry.quantity,
        CountEntry.created_at,
    ).where(CountEntry.session_id == session_id)
    if ids is not None:
        entry_stmt = entry_stmt.where(CountEntry.product_id.in_(ids))
    events: dict[int, list[EntryEvent]] = defaultdict(list)
    for entry_id, pid, kind, qty, at in db.execute(entry_stmt):
        events[pid].append(EntryEvent(at=at, order=entry_id, kind=kind, quantity=qty))

    reported: dict[int, int] = {}
    if snapshot is not None:
        line_stmt = select(Line.product_id, Line.quantity).where(Line.snapshot_id == snapshot.id)
        if ids is not None:
            line_stmt = line_stmt.where(Line.product_id.in_(ids))
        reported = dict(db.execute(line_stmt).all())

    report_at = snapshot.effective_at if snapshot else None
    targets = ids if ids is not None else reported.keys() | events.keys()
    return {
        pid: reconcile(
            events.get(pid, []),
            reported=reported.get(pid, 0),
            in_report=pid in reported,
            report_at=report_at,
        )
        for pid in targets
    }
