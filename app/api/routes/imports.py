from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from app.api.deps import AdminUser, DbSession
from app.core.config import get_settings
from app.schemas.snapshot import (
    CatalogImportOut,
    ImportOut,
    SnapshotImportOut,
    SnapshotOut,
)
from app.schemas.store import StoreOut
from app.services import catalog, snapshots
from app.services.xlsx_parser import (
    ImportKind,
    XlsxFormatError,
    detect_kind,
    parse_catalog,
    parse_stock,
    read_rows,
)

router = APIRouter(prefix="/imports", tags=["imports"])


@router.post("", response_model=ImportOut, status_code=status.HTTP_201_CREATED)
async def import_xlsx(
    db: DbSession,
    admin: AdminUser,
    file: Annotated[UploadFile, File(description="Excel .xlsx")],
    kind: Annotated[ImportKind | None, Form()] = None,
    effective_at: Annotated[datetime | None, Form()] = None,
) -> ImportOut:
    """Sube un Excel. Detecta si es el reporte de existencias o el maestro de códigos."""
    content = await file.read(get_settings().max_upload_bytes + 1)
    if len(content) > get_settings().max_upload_bytes:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "El archivo es demasiado grande.")
    try:
        rows = read_rows(content)
        kind = kind or detect_kind(rows)
        if kind == ImportKind.STOCK:
            parsed = parse_stock(rows)
            if admin.store is not None:
                # Un administrador de tienda solo puede cargar existencias de su tienda.
                other = [s.code for s in parsed.stores if s.code != admin.store.code]
                if other:
                    raise HTTPException(
                        status.HTTP_403_FORBIDDEN,
                        f"El archivo trae existencias de otras tiendas ({', '.join(other)}).",
                    )
            results = snapshots.import_stock(
                db,
                parsed.stores,
                content=content,
                filename=file.filename or "existencias.xlsx",
                effective_at=effective_at,
            )
            db.commit()
            return ImportOut(
                kind=kind,
                skipped_rows=parsed.skipped_rows,
                snapshots=[
                    SnapshotImportOut(
                        snapshot=SnapshotOut.model_validate(r.snapshot),
                        store=StoreOut.model_validate(r.snapshot.store),
                        duplicate=r.duplicate,
                        new_products=r.new_products,
                        lines_without_ean=r.lines_without_ean,
                    )
                    for r in results
                ],
            )
        parsed_catalog = parse_catalog(rows)
        stats = catalog.import_catalog(db, parsed_catalog.lines)
        db.commit()
        return ImportOut(
            kind=kind,
            skipped_rows=parsed_catalog.skipped_rows,
            catalog=CatalogImportOut(
                created=stats.created,
                updated=stats.updated,
                unchanged=stats.unchanged,
                conflicts=stats.conflicts,
                total=len(parsed_catalog.lines),
                columns_swapped=parsed_catalog.columns_swapped,
            ),
        )
    except XlsxFormatError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
