from pydantic import BaseModel, Field
from typing import Optional

class Login(BaseModel):
    username: str
    password: str

class ProductCreate(BaseModel):
    name: str
    barcode: Optional[str] = None
    brand: Optional[str] = None
    category: str = "Outros"
    package_content: Optional[str] = None
    unit: str = "UN"
    stock: int = 0
    min_stock: int = 0
    cost: float = Field(ge=0)
    price: float = Field(ge=0)

class ProductOut(ProductCreate):
    id: int
    model_config = {"from_attributes": True}

class CatalogProductOut(BaseModel):
    barcode: str
    name: str
    brand: Optional[str] = None
    category: str
    package_content: Optional[str] = None
    unit: str
    source: Optional[str] = None
    model_config = {"from_attributes": True}

class SaleLine(BaseModel):
    product_id: int
    quantity: int = Field(gt=0)

class SaleCreate(BaseModel):
    payment_method: str
    items: list[SaleLine]

class StockAdjust(BaseModel):
    product_id: int
    quantity: int
    type: str = "AJUSTE"
    reference: Optional[str] = None
