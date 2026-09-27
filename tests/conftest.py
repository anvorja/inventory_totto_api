"""API de pruebas sobre SQLite en memoria (no toca la base real)."""

import os
import secrets

# Valores aleatorios por ejecución: las pruebas no dependen de ningún secreto fijo.
os.environ["SECRET_KEY"] = secrets.token_urlsafe(48)

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import Product, ProductSource, StockSnapshot, StockSnapshotLine, Store, UserRole
from app.services import auth

PASSWORD = secrets.token_urlsafe(16)


@pytest.fixture
def db() -> Iterator[Session]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    SessionTest = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = SessionTest()

    def override() -> Iterator[Session]:
        yield session

    app.dependency_overrides[get_db] = override
    yield session
    app.dependency_overrides.clear()
    session.close()


@pytest.fixture
def seed(db: Session) -> dict:
    store = Store(code="FQ95", name="TOTTO VILLA GORGONA")
    other = Store(code="XX01", name="OTRA")
    product = Product(
        reference="REF-1", ean="7704682000213", name="MORRAL", source=ProductSource.CATALOG
    )
    db.add_all([store, other, product])
    db.flush()
    snap = StockSnapshot(
        store=store,
        source_filename="x.xlsx",
        file_sha256="x",
        effective_at=datetime.now(UTC) - timedelta(minutes=1),
        line_count=1,
        total_units=3,
    )
    snap.lines.append(StockSnapshotLine(product=product, quantity=3))
    db.add(snap)
    users = {}
    for username, role, store_id in [
        ("admin", UserRole.ADMIN, None),
        ("ana", UserRole.ASESOR, store.id),
        ("beto", UserRole.ASESOR, store.id),
        ("otro", UserRole.ASESOR, other.id),
    ]:
        user, _ = auth.create_user(
            db,
            username=username,
            full_name=username.title(),
            role=role,
            store_id=store_id,
            password=PASSWORD,
        )
        user.must_change_password = False
        users[username] = user
    db.commit()
    return {"store": store, "other": other, "product": product, "users": users}


def client_for(username: str | None) -> TestClient:
    client = TestClient(app, headers={"X-Requested-With": "fetch"})
    if username:
        r = client.post("/api/v1/auth/login", json={"username": username, "password": PASSWORD})
        assert r.status_code == 200, r.text
    return client
