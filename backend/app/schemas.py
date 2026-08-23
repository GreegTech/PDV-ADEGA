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

class ProductUpdate(BaseModel):
    name: Optional[str] = None
    barcode: Optional[str] = None
    brand: Optional[str] = None
    category: Optional[str] = None
    package_content: Optional[str] = None
    unit: Optional[str] = None
    min_stock: Optional[int] = Field(default=None, ge=0)
    price: Optional[float] = Field(default=None, ge=0)

class ProductOut(ProductCreate):
    id: int
    active: bool = True
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

class SupplierCreate(BaseModel):
    name: str = Field(min_length=2, max_length=180)
    document: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    notes: Optional[str] = None

class SupplierOut(SupplierCreate):
    id: int
    active: bool
    model_config = {"from_attributes": True}

class PurchaseLine(BaseModel):
    product_id: int
    quantity: int = Field(gt=0)
    unit_cost: float = Field(gt=0)

class PurchaseCreate(BaseModel):
    supplier_id: int
    document: Optional[str] = None
    items: list[PurchaseLine]

class SaleLine(BaseModel):
    product_id: int
    quantity: int = Field(gt=0)
    # Compatibilidade com clientes antigos: desconto por unidade.
    discount_unit: float = Field(default=0, ge=0)
    # Novo comportamento do PDV: desconto em R$ é o valor total da linha.
    discount_total: Optional[float] = Field(default=None, ge=0)
    discount_percent: Optional[float] = Field(default=None, ge=0, le=100)

class SaleCreate(BaseModel):
    payment_method: str
    items: list[SaleLine]

class StockAdjust(BaseModel):
    product_id: int
    quantity: int
    type: str
    reference: Optional[str] = Field(default=None, max_length=100)
