import json

import pytest
from sqlalchemy import select

from app.models import CountEntry, CountSession, Product, SessionStatus
from app.services.errors import ConflictError
from app.services.legacy_import import LEGACY_COUNTER, import_legacy_count


def test_import_links_eans_creates_missing_and_is_idempotent(db, seed, tmp_path) -> None:
    # Producto del reporte sin EAN (como las referencias nuevas de FQ95)
    sin_ean = Product(reference="MA04NEW-001", name="MORRAL NUEVO", source="stock")
    db.add(sin_ean)
    db.commit()
    backup = tmp_path / "respaldo.json"
    backup.write_text(
        json.dumps(
            {
                "savedAt": "2026-09-26T22:42:15.670Z",
                "master": [
                    {"sku": "7704682000213", "bc": "REF-1", "name": "MORRAL", "n": 2},
                    {"sku": "7704682999999", "bc": "X", "name": "SIN CONTAR", "n": 0},
                ],
                "news": [
                    {"sku": "7704682111111", "bc": "ma04new-001", "name": "MORRAL NUEVO", "n": 4},
                    {"sku": "7704682222222", "bc": "NO-EXISTE", "name": "MORRAL X", "n": 1},
                ],
            }
        )
    )
    r = import_legacy_count(
        db, backup, store_code="fq95", name="Conteo manual", status=SessionStatus.OPEN
    )
    db.commit()
    assert (r.items, r.units, r.matched_by_ean) == (3, 7, 1)
    assert r.ean_linked == ["MA04NEW-001"] and r.created == ["NO-EXISTE"]
    db.refresh(sin_ean)
    assert sin_ean.ean == "7704682111111"
    session = db.get(CountSession, r.session_id)
    assert session.status == SessionStatus.OPEN
    entries = db.scalars(select(CountEntry).where(CountEntry.session_id == r.session_id)).all()
    assert {e.counted_by for e in entries} == {LEGACY_COUNTER}
    assert entries[0].created_at.strftime("%Y-%m-%d %H:%M") == "2026-09-26 22:42"

    with pytest.raises(ConflictError):
        import_legacy_count(
            db, backup, store_code="FQ95", name="Conteo manual", status=SessionStatus.OPEN
        )
