from app.services.comparison import ComparisonLine, LineStatus, classify, summarize


def line(
    expected: int, counted: int, in_snapshot: bool = True, ean: str | None = "1"
) -> ComparisonLine:
    return ComparisonLine(
        product_id=0,
        reference="R",
        ean=ean,
        name="P",
        business_unit=None,
        size=None,
        color_name=None,
        expected=expected,
        counted=counted,
        status=classify(expected, counted, in_snapshot),
    )


def test_classify() -> None:
    assert classify(2, 2, True) == LineStatus.OK
    assert classify(3, 1, True) == LineStatus.MISSING
    assert classify(1, 3, True) == LineStatus.SURPLUS
    assert classify(0, 2, False) == LineStatus.UNEXPECTED


def test_summary_accuracy_and_buckets() -> None:
    lines = [
        line(3, 3),
        line(4, 1),
        line(1, 2),
        line(0, 5, in_snapshot=False),
        line(2, 0, ean=None),
    ]
    s = summarize(lines)
    assert s.expected_units == 10
    assert s.counted_units == 11
    assert s.matched_units == 3 + 1 + 1
    assert s.accuracy == 0.5
    assert s.expected_lines == 4
    assert s.progress == 0.75
    assert s.lines_without_ean == 1
    assert s.buckets[LineStatus.MISSING].lines == 2
    assert s.buckets[LineStatus.MISSING].units == 5
    assert s.buckets[LineStatus.SURPLUS].units == 1
    assert s.buckets[LineStatus.UNEXPECTED].units == 5
