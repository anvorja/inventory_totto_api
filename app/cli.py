"""Carga Excel desde la terminal: `uv run python -m app.cli import archivo.xlsx [...]`."""

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models import Store, UserRole
from app.services import auth, catalog, snapshots
from app.services.errors import DomainError
from app.services.xlsx_parser import (
    ImportKind,
    XlsxFormatError,
    detect_kind,
    parse_catalog,
    parse_stock,
    read_rows,
)


def timestamp_from_filename(name: str) -> datetime | None:
    """El export del sistema trae la hora en el nombre: 'data - 2026-09-26T101702.972.xlsx'."""
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})T(\d{2})(\d{2})(\d{2})?", name)
    if not m:
        return None
    y, mo, d, h, mi, sec = (int(g) if g else 0 for g in m.groups())
    return datetime(y, mo, d, h, mi, sec).astimezone()  # hora local del equipo


def import_file(path: Path) -> None:
    content = path.read_bytes()
    rows = read_rows(content)
    kind = detect_kind(rows)
    with SessionLocal() as db:
        if kind == ImportKind.CATALOG:
            parsed = parse_catalog(rows)
            stats = catalog.import_catalog(db, parsed.lines)
            db.commit()
            print(f"✔ Maestro de códigos {path.name}: {stats}")
            if parsed.columns_swapped:
                print("  ⚠ Encabezados invertidos: BARCODE debe ser el EAN y SKU la referencia.")
            return
        results = snapshots.import_stock(
            db,
            parse_stock(rows).stores,
            content=content,
            filename=path.name,
            effective_at=timestamp_from_filename(path.name),
        )
        db.commit()
        for r in results:
            s = r.snapshot
            state = "ya existía" if r.duplicate else "cargado"
            print(
                f"✔ Existencias {s.store.code} {state}: {s.line_count} referencias, "
                f"{s.total_units} und, {r.new_products} productos nuevos, "
                f"{r.lines_without_ean} sin EAN"
            )


def create_user(username: str, name: str, role: str, store_code: str | None) -> None:
    with SessionLocal() as db:
        store_id = None
        if store_code:
            store = db.scalars(select(Store).where(Store.code == store_code.upper())).first()
            if store is None:
                sys.exit(f"✘ No existe la tienda {store_code}")
            store_id = store.id
        try:
            user, temporary = auth.create_user(
                db, username=username, full_name=name, role=UserRole(role), store_id=store_id
            )
        except DomainError as exc:
            sys.exit(f"✘ {exc.message}")
        db.commit()
        print(f"✔ Usuario '{user.username}' ({user.role}) creado.")
        print(f"  Contraseña temporal: {temporary}  (se pedirá cambiarla al ingresar)")


def main() -> None:
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="cmd", required=True)
    imp = sub.add_parser("import", help="Importa uno o varios Excel (tipo autodetectado)")
    imp.add_argument("files", nargs="+", type=Path)
    cu = sub.add_parser("create-user", help="Crea un usuario con contraseña temporal")
    cu.add_argument("username")
    cu.add_argument("--name", required=True, help="Nombre completo")
    cu.add_argument("--role", choices=[r.value for r in UserRole], default=UserRole.ASESOR.value)
    cu.add_argument("--store", help="Código de tienda (p. ej. FQ95). Vacío = todas")
    args = parser.parse_args()
    if args.cmd == "create-user":
        create_user(args.username, args.name, args.role, args.store)
        return
    # El maestro de códigos primero, para que las existencias ya encuentren los EAN.
    files = sorted(args.files, key=lambda p: detect_kind(read_rows(p.read_bytes())) != "catalog")
    for path in files:
        try:
            import_file(path)
        except XlsxFormatError as exc:
            print(f"✘ {path.name}: {exc}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
