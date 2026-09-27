from pydantic import Field

from app.models import ProductSource
from app.schemas.base import ApiModel


class ProductOut(ApiModel):
    id: int
    reference: str | None
    ean: str | None
    name: str
    business_unit: str | None
    size: str | None
    color_code: str | None
    color_name: str | None
    source: ProductSource


class ProductCreate(ApiModel):
    ean: str | None = Field(default=None, max_length=14)
    reference: str | None = Field(default=None, max_length=40)
    name: str | None = Field(default=None, max_length=200)
