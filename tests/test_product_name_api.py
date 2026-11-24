from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ProductNameChange
from app.services import snapshots
from app.services.xlsx_parser import StockLine, StoreStock
from tests.conftest import client_for

API = "/api/v1"


def test_only_admin_renames_and_history_is_kept(seed: dict, db: Session) -> None:
    pid = seed["product"].id
    admin, ana = client_for("admin"), client_for("ana")

    # Un asesor no puede, ni siquiera con permiso para editar códigos.
    admin.patch(f"{API}/users/{seed['users']['ana'].id}", json={"canEditBarcodes": True})
    r = ana.patch(f"{API}/products/{pid}/name", json={"name": "OTRO"})
    assert r.status_code == 403 and r.json()["code"] == "forbidden"

    # Admin: se normalizan los espacios, queda fijado y en el historial.
    r = admin.patch(f"{API}/products/{pid}/name", json={"name": "  MORRAL   ESCOLAR  AZUL "})
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "MORRAL ESCOLAR AZUL"
    assert r.json()["nameLocked"] is True
    change = db.scalars(select(ProductNameChange)).one()
    assert (change.old_name, change.new_name, change.changed_by) == (
        "MORRAL",
        "MORRAL ESCOLAR AZUL",
        "Admin",
    )

    # Mismo nombre: sin cambios ni historial nuevo. Muy corto: error. Inexistente: 404.
    same = admin.patch(f"{API}/products/{pid}/name", json={"name": "MORRAL ESCOLAR AZUL"})
    assert same.status_code == 200
    assert db.scalars(select(ProductNameChange)).all() == [change]
    assert admin.patch(f"{API}/products/{pid}/name", json={"name": " a "}).status_code == 400
    assert admin.patch(f"{API}/products/999999/name", json={"name": "X Y"}).status_code == 404


def test_stock_import_keeps_locked_name(seed: dict, db: Session) -> None:
    product = seed["product"]
    admin = client_for("admin")

    def load(name: str, color: str) -> None:
        stock = StoreStock(code="FQ95", name="TOTTO VILLA GORGONA")
        stock.lines["REF-1"] = StockLine(reference="REF-1", quantity=1, name=name, color_name=color)
        snapshots.import_stock(
            db, [stock], content=f"{name}{color}".encode(), filename="x.xlsx", effective_at=None
        )
        db.commit()
        db.refresh(product)

    # Sin editar, la carga actualiza el nombre como siempre.
    load("MORRAL DEL SISTEMA", "NEGRO")
    assert product.name == "MORRAL DEL SISTEMA"

    # Tras la corrección del admin, la carga ya no lo pisa, pero sí actualiza lo demás.
    admin.patch(f"{API}/products/{product.id}/name", json={"name": "MORRAL CORREGIDO"})
    load("MORRAL DEL SISTEMA", "AZUL")
    assert product.name == "MORRAL CORREGIDO"
    assert product.color_name == "AZUL"
