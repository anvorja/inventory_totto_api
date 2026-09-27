"""Cruce entre lo contado y lo que el sistema dice que debería haber."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Product, StockSnapshot
from app.services.reconcile import load_states


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
    expected: int  # esperado ahora: reporte − ventas registradas después del reporte
    counted: int  # contado que sigue en tienda (descontando ventas posteriores al conteo)
    status: LineStatus
    reported: int | None = None  # lo que dice el reporte de existencias
    sold: int = 0  # ventas registradas después de la hora del reporte

    def __post_init__(self) -> None:
        if self.reported is None:
            self.reported = self.expected

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
    sold_units: int = 0  # vendidas durante el conteo (ya descontadas de lo esperado)


def classify(expected: int, counted: int, in_snapshot: bool) -> LineStatus:
    if not in_snapshot:
        return LineStatus.UNEXPECTED
    if counted == expected:
        return LineStatus.OK
    return LineStatus.MISSING if counted < expected else LineStatus.SURPLUS


def build_comparison(
    db: Session, session_id: int, snapshot: StockSnapshot | None
) -> tuple[ComparisonSummary, list[ComparisonLine]]:
    states = load_states(db, session_id, snapshot)
    # Un producto fuera del reporte que ya no está en tienda no aporta nada a comparar.
    states = {pid: st for pid, st in states.items() if st.in_report or st.counted > 0}
    products = (
        {p.id: p for p in db.scalars(select(Product).where(Product.id.in_(states)))}
        if states
        else {}
    )

    lines: list[ComparisonLine] = []
    for pid, st in states.items():
        p = products[pid]
        lines.append(
            ComparisonLine(
                product_id=pid,
                reference=p.reference,
                ean=p.ean,
                name=p.name,
                business_unit=p.business_unit,
                size=p.size,
                color_name=p.color_name,
                expected=st.expected,
                counted=st.counted,
                status=classify(st.expected, st.counted, st.in_report),
                reported=st.reported,
                sold=st.sold,
            )
        )
    lines.sort(key=lambda line: (-abs(line.difference), line.name, line.reference or ""))
    return summarize(lines), lines


def summarize(lines: list[ComparisonLine]) -> ComparisonSummary:
    buckets = {status: StatusBucket() for status in LineStatus}
    expected_units = counted_units = matched = expected_lines = touched = no_ean = sold = 0
    for line in lines:
        sold += line.sold
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
        sold_units=sold,
    )
