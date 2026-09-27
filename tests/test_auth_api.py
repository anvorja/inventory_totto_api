from app.core.security import hash_password, verify_password
from tests.conftest import PASSWORD, client_for

API = "/api/v1"


def test_password_hashing() -> None:
    h = hash_password("secreto-123")
    assert verify_password("secreto-123", h)
    assert not verify_password("otra", h)


def test_requires_login(seed: dict) -> None:
    anon = client_for(None)
    assert anon.get(f"{API}/stores").status_code == 401


def test_login_sets_httponly_cookie_and_me(seed: dict) -> None:
    c = client_for(None)
    r = c.post(f"{API}/auth/login", json={"username": "ANA ", "password": PASSWORD})
    assert r.status_code == 200
    assert "httponly" in r.headers["set-cookie"].lower()
    assert r.json()["role"] == "asesor"
    assert c.get(f"{API}/auth/me").json()["username"] == "ana"
    c.post(f"{API}/auth/logout")
    assert c.get(f"{API}/auth/me").status_code == 401


def test_wrong_password_and_lockout(seed: dict) -> None:
    c = client_for(None)
    for _ in range(5):
        r = c.post(f"{API}/auth/login", json={"username": "ana", "password": "mala"})
        assert r.status_code == 401
    r = c.post(f"{API}/auth/login", json={"username": "ana", "password": PASSWORD})
    assert r.status_code == 429


def test_csrf_header_required(seed: dict) -> None:
    from fastapi.testclient import TestClient

    from app.main import app

    bare = TestClient(app)
    r = bare.post(f"{API}/auth/login", json={"username": "ana", "password": PASSWORD})
    assert r.status_code == 403 and r.json()["code"] == "csrf"


def test_asesor_permissions(seed: dict) -> None:
    store_id = seed["store"].id
    admin, ana = client_for("admin"), client_for("ana")
    # Solo admin crea conteos
    assert ana.post(f"{API}/sessions", json={"storeId": store_id, "name": "X"}).status_code == 403
    sid = admin.post(f"{API}/sessions", json={"storeId": store_id, "name": "X"}).json()["id"]
    # Asesor cuenta; el nombre sale del usuario, no del cliente
    r = ana.post(f"{API}/sessions/{sid}/scans", json={"code": "7704682000213", "countedBy": "Hack"})
    assert r.status_code == 201, r.text
    entry = r.json()["entry"]
    assert entry["countedBy"] == "Ana"
    # Asesor ve diferencias pero no exporta ni cierra ni sube Excel
    assert ana.get(f"{API}/sessions/{sid}/comparison").status_code == 200
    assert ana.get(f"{API}/sessions/{sid}/export").status_code == 403
    assert ana.patch(f"{API}/sessions/{sid}", json={"status": "closed"}).status_code == 403
    assert ana.post(f"{API}/imports", files={"file": ("a.xlsx", b"x")}).status_code == 403
    assert ana.get(f"{API}/users").status_code == 403
    # Otro asesor no puede deshacer lecturas ajenas; el admin sí
    beto = client_for("beto")
    assert beto.delete(f"{API}/sessions/{sid}/scans/{entry['id']}").status_code == 403
    assert admin.delete(f"{API}/sessions/{sid}/scans/{entry['id']}").status_code == 200


def test_store_scoping(seed: dict) -> None:
    store_id = seed["store"].id
    admin, otro = client_for("admin"), client_for("otro")
    sid = admin.post(f"{API}/sessions", json={"storeId": store_id, "name": "X"}).json()["id"]
    assert [s["code"] for s in otro.get(f"{API}/stores").json()] == ["XX01"]
    assert otro.get(f"{API}/sessions/{sid}").status_code == 404
    assert (
        otro.post(f"{API}/sessions/{sid}/scans", json={"code": "7704682000213"}).status_code == 404
    )
    assert len(admin.get(f"{API}/stores").json()) == 2


def test_user_admin_flow(seed: dict) -> None:
    admin = client_for("admin")
    r = admin.post(
        f"{API}/users",
        json={
            "username": "Carla",
            "fullName": "Carla Pérez",
            "role": "asesor",
            "storeId": seed["store"].id,
        },
    )
    assert r.status_code == 201, r.text
    temp = r.json()["temporaryPassword"]
    uid = r.json()["user"]["id"]
    carla = client_for(None)
    assert (
        carla.post(f"{API}/auth/login", json={"username": "carla", "password": temp}).status_code
        == 200
    )
    # Con contraseña temporal no puede operar hasta cambiarla
    r = carla.get(f"{API}/stores")
    assert r.status_code == 403 and r.json()["code"] == "password_change_required"
    r = carla.post(
        f"{API}/auth/change-password",
        json={"currentPassword": temp, "newPassword": "nueva-clave-1"},
    )
    assert r.status_code == 200 and r.json()["mustChangePassword"] is False
    assert carla.get(f"{API}/stores").status_code == 200
    # Desactivar cierra su sesión
    assert admin.patch(f"{API}/users/{uid}", json={"isActive": False}).status_code == 200
    assert carla.get(f"{API}/stores").status_code == 401


def test_cannot_remove_last_admin(seed: dict) -> None:
    admin = client_for("admin")
    me = admin.get(f"{API}/auth/me").json()["id"]
    r = admin.patch(f"{API}/users/{me}", json={"role": "asesor"})
    assert r.status_code == 409


def test_sales_flow_and_permissions(seed: dict) -> None:
    store_id, product_id = seed["store"].id, seed["product"].id
    admin, ana, beto = client_for("admin"), client_for("ana"), client_for("beto")
    sid = admin.post(f"{API}/sessions", json={"storeId": store_id, "name": "X"}).json()["id"]

    # Búsqueda por nombre con la situación del producto en el conteo
    found = ana.get(f"{API}/sessions/{sid}/products", params={"q": "morr"}).json()
    assert found[0]["product"]["id"] == product_id
    assert (found[0]["reported"], found[0]["expected"], found[0]["counted"]) == (3, 3, 0)

    # Asesora cuenta 3 y luego se vende 1: esperado y contado bajan a 2
    assert (
        ana.post(
            f"{API}/sessions/{sid}/scans", json={"productId": product_id, "quantity": 3}
        ).status_code
        == 201
    )
    r = ana.post(f"{API}/sessions/{sid}/sales", json={"productId": product_id, "quantity": 1})
    assert r.status_code == 201, r.text
    sale = r.json()
    assert (sale["expected"], sale["counted"], sale["sold"], sale["status"]) == (2, 2, 1, "ok")
    assert sale["entry"]["kind"] == "sale"

    s = admin.get(f"{API}/sessions/{sid}").json()
    assert (s["countedUnits"], s["soldUnits"]) == (3, 1)
    line = admin.get(f"{API}/sessions/{sid}/comparison").json()["lines"][0]
    assert (line["reported"], line["sold"], line["expected"], line["counted"]) == (3, 1, 2, 2)
    assert admin.get(f"{API}/sessions/{sid}/comparison").json()["summary"]["soldUnits"] == 1

    # Otro asesor no deshace la venta ajena; la autora sí
    assert beto.delete(f"{API}/sessions/{sid}/scans/{sale['entry']['id']}").status_code == 403
    undo = ana.delete(f"{API}/sessions/{sid}/scans/{sale['entry']['id']}").json()
    assert (undo["kind"], undo["expected"], undo["counted"]) == ("sale", 3, 3)

    # Validaciones
    assert (
        ana.post(
            f"{API}/sessions/{sid}/sales", json={"productId": product_id, "quantity": 0}
        ).status_code
        == 422
    )
    admin.patch(f"{API}/sessions/{sid}", json={"status": "closed"})
    assert (
        ana.post(f"{API}/sessions/{sid}/sales", json={"productId": product_id}).status_code == 409
    )
