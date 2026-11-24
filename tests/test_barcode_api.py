from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BarcodeChange, Product, ProductSource
from tests.conftest import client_for

API = "/api/v1"
OLD = "7704682000213"  # EAN del producto de prueba
NEW = "7704682999990"


def _grant(admin, user_id: int, allowed: bool) -> None:
    r = admin.patch(f"{API}/users/{user_id}", json={"canEditBarcodes": allowed})
    assert r.status_code == 200, r.text
    assert r.json()["canEditBarcodes"] is allowed


def test_asesor_needs_permission_granted_by_admin(seed: dict, db: Session) -> None:
    pid = seed["product"].id
    ana_id = seed["users"]["ana"].id
    admin, ana = client_for("admin"), client_for("ana")

    # Sin permiso: el asesor no puede editar ni concederse el permiso.
    assert ana.get(f"{API}/auth/me").json()["canEditBarcodes"] is False
    r = ana.patch(f"{API}/products/{pid}/ean", json={"ean": NEW})
    assert r.status_code == 403 and r.json()["code"] == "forbidden"
    assert ana.patch(f"{API}/users/{ana_id}", json={"canEditBarcodes": True}).status_code == 403

    # El admin lo concede: ahora sí puede, y queda en el historial a su nombre.
    _grant(admin, ana_id, True)
    assert ana.get(f"{API}/auth/me").json()["canEditBarcodes"] is True
    r = ana.patch(f"{API}/products/{pid}/ean", json={"ean": f" {NEW} "})
    assert r.status_code == 200, r.text
    assert r.json()["ean"] == NEW
    assert ana.get(f"{API}/products/lookup/{NEW}").json()["id"] == pid
    assert ana.get(f"{API}/products/lookup/{OLD}").status_code == 404
    change = db.scalars(select(BarcodeChange)).one()
    assert (change.old_ean, change.new_ean, change.changed_by) == (OLD, NEW, "Ana")

    # El admin lo retira: vuelve a estar prohibido.
    _grant(admin, ana_id, False)
    assert ana.patch(f"{API}/products/{pid}/ean", json={"ean": OLD}).status_code == 403


def test_admin_can_always_edit_and_validations(seed: dict, db: Session) -> None:
    pid = seed["product"].id
    other = Product(
        reference="REF-2", ean="7704682111110", name="MALETA", source=ProductSource.CATALOG
    )
    db.add(other)
    db.commit()
    admin = client_for("admin")

    # Formato inválido
    r = admin.patch(f"{API}/products/{pid}/ean", json={"ean": "ABC123"})
    assert r.status_code == 400
    # Código de otro producto (también con cero inicial de más) → conflicto que lo nombra
    for code in ("7704682111110", "07704682111110"):
        r = admin.patch(f"{API}/products/{pid}/ean", json={"ean": code})
        assert r.status_code == 409, code
        assert "MALETA (REF-2)" in r.json()["detail"]
    # Mismo código: no cambia nada ni deja historial
    assert admin.patch(f"{API}/products/{pid}/ean", json={"ean": OLD}).status_code == 200
    assert db.scalars(select(BarcodeChange)).first() is None
    # Producto inexistente
    assert admin.patch(f"{API}/products/999999/ean", json={"ean": NEW}).status_code == 404
    # Cambio válido
    r = admin.patch(f"{API}/products/{pid}/ean", json={"ean": NEW})
    assert r.status_code == 200 and r.json()["ean"] == NEW


def test_scans_after_correction_count_the_same_product(seed: dict) -> None:
    store_id, pid = seed["store"].id, seed["product"].id
    admin = client_for("admin")
    sid = admin.post(f"{API}/sessions", json={"storeId": store_id, "name": "X"}).json()["id"]
    assert admin.post(f"{API}/sessions/{sid}/scans", json={"code": OLD}).status_code == 201

    admin.patch(f"{API}/products/{pid}/ean", json={"ean": NEW})
    r = admin.post(f"{API}/sessions/{sid}/scans", json={"code": NEW})
    assert r.status_code == 201, r.text
    # La lectura previa (con el código viejo) y la nueva suman al mismo producto.
    assert r.json()["counted"] == 2
