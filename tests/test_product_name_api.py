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


def test_stock_import_warns_and_releases(seed: dict, db: Session) -> None:
    product = seed["product"]
    admin = client_for("admin")

    def load(name: str, color: str) -> snapshots.SnapshotImportResult:
        stock = StoreStock(code="FQ95", name="TOTTO VILLA GORGONA")
        stock.lines["REF-1"] = StockLine(reference="REF-1", quantity=1, name=name, color_name=color)
        [result] = snapshots.import_stock(
            db, [stock], content=f"{name}{color}".encode(), filename="x.xlsx", effective_at=None
        )
        db.commit()
        db.refresh(product)
        return result

    # Sin editar, la carga actualiza el nombre como siempre y no avisa nada.
    r = load("MORRAL DEL SISTEMA", "NEGRO")
    assert (product.name, product.source_name, r.name_conflicts) == (
        "MORRAL DEL SISTEMA",
        "MORRAL DEL SISTEMA",
        [],
    )

    # Corregido por el admin: la carga no lo pisa, avisa la diferencia y actualiza lo demás.
    admin.patch(f"{API}/products/{product.id}/name", json={"name": "MORRAL CORREGIDO"})
    r = load("MORRAL DEL SISTEMA", "AZUL")
    assert product.name == "MORRAL CORREGIDO" and product.name_locked
    assert product.color_name == "AZUL"
    assert [(c.product.id, c.excel_name) for c in r.name_conflicts] == [
        (product.id, "MORRAL DEL SISTEMA")
    ]
    renamed = admin.get(f"{API}/products/renamed").json()
    assert [(p["name"], p["sourceName"]) for p in renamed] == [
        ("MORRAL CORREGIDO", "MORRAL DEL SISTEMA")
    ]

    # El sistema se pone al día: el nombre se libera solo, sin aviso.
    r = load("MORRAL CORREGIDO", "AZUL")
    assert not product.name_locked
    assert (r.name_conflicts, r.names_released) == ([], 1)
    assert admin.get(f"{API}/products/renamed").json() == []


def test_back_to_system_name_unlocks(seed: dict, db: Session) -> None:
    product = seed["product"]
    product.source_name = "MORRAL DEL SISTEMA"
    db.commit()
    admin = client_for("admin")

    r = admin.patch(f"{API}/products/{product.id}/name", json={"name": "MORRAL CORREGIDO"})
    assert r.json()["nameLocked"] is True
    # "Volver al nombre del sistema" = escribir el mismo nombre que trae el Excel.
    r = admin.patch(f"{API}/products/{product.id}/name", json={"name": "MORRAL DEL SISTEMA"})
    assert r.json()["name"] == "MORRAL DEL SISTEMA"
    assert r.json()["nameLocked"] is False


def _stock_xlsx(name: str) -> bytes:
    import io

    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["Punto de Venta", "Código Producto Largo", "Nombre Producto", "Disponible"])
    ws.append(["FQ95 - TOTTO VILLA GORGONA", "REF-1", name, 2])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_import_endpoint_reports_name_conflicts(seed: dict) -> None:
    product = seed["product"]
    admin = client_for("admin")
    admin.patch(f"{API}/products/{product.id}/name", json={"name": "MORRAL CORREGIDO"})

    r = admin.post(
        f"{API}/imports",
        files={"file": ("existencias.xlsx", _stock_xlsx("MORRAL DEL SISTEMA"))},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert [(c["product"]["name"], c["excelName"]) for c in body["nameConflicts"]] == [
        ("MORRAL CORREGIDO", "MORRAL DEL SISTEMA")
    ]
    assert body["namesReleased"] == 0
