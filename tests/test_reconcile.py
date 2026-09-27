from datetime import UTC, datetime, timedelta

from app.models import EntryKind
from app.services.reconcile import EntryEvent, reconcile

REPORT = datetime(2026, 9, 26, 10, 0, tzinfo=UTC)
_n = 0


def ev(minutes: int, kind: EntryKind, qty: int) -> EntryEvent:
    global _n
    _n += 1
    return EntryEvent(at=REPORT + timedelta(minutes=minutes), order=_n, kind=kind, quantity=qty)


C, S = EntryKind.COUNT, EntryKind.SALE


def state(events, reported=3):
    return reconcile(events, reported=reported, in_report=True, report_at=REPORT)


def test_sale_after_report_before_counting_reduces_expected_only() -> None:
    # Reporte 3, se vende 1 y luego se cuentan las 2 que quedan: cuadra.
    st = state([ev(10, S, 1), ev(20, C, 2)])
    assert (st.expected, st.counted, st.sold) == (2, 2, 1)


def test_sale_after_counting_reduces_expected_and_counted() -> None:
    # Se cuentan 3 y luego se vende 1: siguen cuadrando (2 y 2), sin sobrante falso.
    st = state([ev(10, C, 3), ev(20, S, 1)])
    assert (st.expected, st.counted) == (2, 2)


def test_sale_before_report_is_not_discounted_twice() -> None:
    # La venta ya está en el reporte (ocurrió antes): no se resta de lo esperado.
    st = state([ev(-30, S, 1), ev(10, C, 3)])
    assert (st.expected, st.counted, st.sold) == (3, 3, 0)


def test_sale_before_report_after_counting_only_reduces_counted() -> None:
    # Contado antes del reporte y vendido antes del reporte: el reporte ya la descontó.
    st = state([ev(-60, C, 3), ev(-30, S, 1)], reported=2)
    assert (st.expected, st.counted) == (2, 2)


def test_partial_count_then_sale_assumes_counted_unit() -> None:
    # Se contó 1 de 3 y se vendió 2: se asume que 1 de las vendidas era la contada.
    st = state([ev(10, C, 1), ev(20, S, 2), ev(30, C, 1)])
    assert (st.expected, st.counted, st.sold_after_counting) == (1, 1, 1)


def test_corrections_and_undo_semantics() -> None:
    st = state([ev(10, C, 2), ev(11, C, -1), ev(20, S, 1)])
    assert (st.counted_raw, st.counted, st.expected) == (1, 0, 2)


def test_expected_never_negative_and_no_report() -> None:
    assert state([ev(10, S, 5)], reported=2).expected == 0
    st = reconcile([ev(10, C, 1), ev(20, S, 1)], reported=0, in_report=False, report_at=None)
    assert (st.expected, st.counted, st.sold, st.in_report) == (0, 0, 1, False)
