from pathlib import Path

import pytest

from app.services.xlsx_parser import (
    ImportKind,
    XlsxFormatError,
    clean_ean,
    detect_kind,
    parse_catalog,
    parse_stock,
    read_rows,
    split_store,
    to_int,
)

ROOT = Path(__file__).resolve().parents[2]
STOCK_FILE = ROOT / "data - 2026-09-26T101702.972.xlsx"
CATALOG_FILE = ROOT / "BarrcodeFQ95.xlsx"


@pytest.mark.skipif(not STOCK_FILE.exists(), reason="archivo de ejemplo no disponible")
def test_parse_real_stock_file() -> None:
    rows = read_rows(STOCK_FILE.read_bytes())
    assert detect_kind(rows) == ImportKind.STOCK
    result = parse_stock(rows)
    assert len(result.stores) == 1
    store = result.stores[0]
    assert (store.code, store.name) == ("FQ95", "TOTTO VILLA GORGONA")
    assert len(store.lines) == 1442
    assert store.total_units == 3815  # coincide con la fila "Total" del export
    # Las referencias con espacios al final quedan normalizadas.
    assert "AC50COE001-2610Z-KMN" in store.lines
    assert result.skipped_rows == 2  # fila Total + nota de filtros


@pytest.mark.skipif(not CATALOG_FILE.exists(), reason="archivo de ejemplo no disponible")
def test_parse_real_catalog_detects_inverted_columns() -> None:
    rows = read_rows(CATALOG_FILE.read_bytes())
    assert detect_kind(rows) == ImportKind.CATALOG
    result = parse_catalog(rows)
    assert len(result.lines) == 2347
    first = result.lines[0]
    # El archivo original trae los encabezados invertidos: se corrige y se informa.
    assert result.columns_swapped is True
    assert first.reference == "AC53IND398-2510Z-N01"
    assert first.ean == "7704682000213"


@pytest.mark.parametrize(
    "headers",
    [
        ("SKU", "BARCODE", "NOMBRE PRODUCTO"),  # nombres corregidos
        ("Código Producto Largo", "BARCODE", "NOMBRE PRODUCTO"),
        ("Referencia", "EAN", "Nombre"),
    ],
)
def test_catalog_with_correct_headers_is_not_swapped(headers: tuple[str, str, str]) -> None:
    rows = [headers, ("ab-1", "7704682000213", "Morral")]
    result = parse_catalog(rows)
    line = result.lines[0]
    assert result.columns_swapped is False
    assert (line.ean, line.reference, line.name) == ("7704682000213", "AB-1", "Morral")


def test_catalog_with_inverted_headers_is_swapped() -> None:
    rows = [("BARCODE", "SKU", "NOMBRE PRODUCTO"), ("AB-1", "7704682000213", "Morral")]
    result = parse_catalog(rows)
    assert result.columns_swapped is True
    assert (result.lines[0].ean, result.lines[0].reference) == ("7704682000213", "AB-1")


def test_stock_header_not_on_first_row_and_duplicates_summed() -> None:
    rows = [
        ("Reporte de existencias",),
        (),
        ("Punto de Venta", "Código Producto Largo", "Disponible"),
        ("FQ95 - TOTTO X", "REF-1", 2),
        ("FQ95 - TOTTO X", "REF-1 ", "3"),
        ("Total", None, 5),
    ]
    store = parse_stock(rows).stores[0]
    assert store.lines["REF-1"].quantity == 5


def test_unknown_file_raises() -> None:
    with pytest.raises(XlsxFormatError):
        detect_kind([("a", "b")])


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("7704682000213", "7704682000213"),
        (7704682000213, "7704682000213"),
        (7704682000213.0, "7704682000213"),
        ("77046 82000213", "7704682000213"),
        ("AC53IND398", None),
        ("123", None),
    ],
)
def test_clean_ean(raw: object, expected: str | None) -> None:
    assert clean_ean(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"), [(3, 3), ("3", 3), ("1.234", 1234), ("3,0", 3), ("", None), ("x", None)]
)
def test_to_int(raw: object, expected: int | None) -> None:
    assert to_int(raw) == expected


def test_split_store() -> None:
    assert split_store("FQ95 - TOTTO VILLA GORGONA") == ("FQ95", "TOTTO VILLA GORGONA")
    assert split_store("Total")[0] == "TOTAL"
