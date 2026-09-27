from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUser, DbSession
from app.models import Product
from app.schemas.product import ProductCreate, ProductOut
from app.services import catalog

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=list[ProductOut])
def search(db: DbSession, _: CurrentUser, q: str = "", limit: int = 20) -> list[Product]:
    return catalog.search_products(db, q, min(limit, 50))


@router.get("/lookup/{code}", response_model=ProductOut)
def lookup(code: str, db: DbSession, _: CurrentUser) -> Product:
    product = catalog.find_by_code(db, code)
    if product is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Este código no está en el catálogo.")
    return product


@router.post("", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
def register(body: ProductCreate, db: DbSession, _: CurrentUser) -> Product:
    product = catalog.register_product(db, ean=body.ean, reference=body.reference, name=body.name)
    db.commit()
    return product
