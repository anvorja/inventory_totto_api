"""Cruce entre lo contado y lo que el sistema dice que debería haber."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import CountEntry, Product, StockSnapshot
from app.models import StockSnapshotLine as Line


class LineStatus(StrEnum):
    OK = "ok"  # contado == esperado
    MISSING = "missing"  # faltante: contado < esperado
    SURPLUS = "surplus"  # sobrante: contado > esperado (y se esperaba algo)
    UNEXPECTED = "unexpected"  # contado pero no está en el reporte de existencias


@dataclass
class ComparisonLine:
    product_id: int
    reference: str | None
    ean: str | None
    name: str
    business_unit: str | None
    size: str | None
    color_name: str | None
    expected: int
    counted: int
    status: LineStatus

    @property
    def difference(self) -> int:
        return self.counted - self.expected


@dataclass
class StatusBucket:
    lines: int = 0
    units: int = 0


@dataclass
class ComparisonSummary:
    expected_units: int
    counted_units: int
    matched_units: int
    accuracy: float  # unidades cuadradas / unidades esperadas
    progress: float  # referencias esperadas con al menos 1 contada / referencias esperadas
    expected_lines: int
    lines_without_ean: int
    buckets: dict[LineStatus, StatusBucket] = field(default_factory=dict)


def classify(expected: int, counted: int, in_snapshot: bool) -> LineStatus:
    if not in_snapshot:
        return LineStatus.UNEXPECTED
    if counted == expected:
        return LineStatus.OK
    return LineStatus.MISSING if counted < expected else LineStatus.SURPLUS


def build_comparison(
    db: Session, session_id: int, snapshot: StockSnapshot | None
) -> tuple[ComparisonSummary, list[ComparisonLine]]:
    counted_rows = db.execute(
        select(CountEntry.product_id, func.sum(CountEntry.quantity))
        .where(CountEntry.session_id == session_id)
        .group_by(CountEntry.product_id)
    ).all()
    counted = {pid: int(n) for pid, n in counted_rows if n}

    expected: dict[int, int] = {}
    if snapshot is not None:
        expected = dict(
            db.execute(
                select(Line.product_id, Line.quantity).where(Line.snapshot_id == snapshot.id)
            ).all()
        )

    ids = expected.keys() | counted.keys()
    products = (
        {p.id: p for p in db.scalars(select(Product).where(Product.id.in_(ids)))} if ids else {}
    )

    lines: list[ComparisonLine] = []
    for pid in ids:
        p = products[pid]
        exp = expected.get(pid, 0)
        cnt = counted.get(pid, 0)
        lines.append(
            ComparisonLine(
                product_id=pid,
                reference=p.reference,
                ean=p.ean,
                name=p.name,
                business_unit=p.business_unit,
                size=p.size,
                color_name=p.color_name,
                expected=exp,
                counted=cnt,
                status=classify(exp, cnt, pid in expected),
            )
        )
    lines.sort(key=lambda line: (-abs(line.difference), line.name, line.reference or ""))
    return summarize(lines), lines


def summarize(lines: list[ComparisonLine]) -> ComparisonSummary:
    buckets = {status: StatusBucket() for status in LineStatus}
    expected_units = counted_units = matched = expected_lines = touched = no_ean = 0
    for line in lines:
        bucket = buckets[line.status]
        bucket.lines += 1
        bucket.units += abs(line.difference) if line.status != LineStatus.OK else line.counted
        counted_units += line.counted
        if line.status == LineStatus.UNEXPECTED:
            continue
        expected_lines += 1
        exp = max(line.expected, 0)
        expected_units += exp
        matched += min(exp, line.counted)
        touched += 1 if line.counted > 0 else 0
        no_ean += 1 if not line.ean else 0
    return ComparisonSummary(
        expected_units=expected_units,
        counted_units=counted_units,
        matched_units=matched,
        accuracy=round(matched / expected_units, 4) if expected_units else 0.0,
        progress=round(touched / expected_lines, 4) if expected_lines else 0.0,
        expected_lines=expected_lines,
        lines_without_ean=no_ean,
        buckets=buckets,
    )
