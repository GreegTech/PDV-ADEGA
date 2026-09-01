from pydantic import BaseModel, Field
from typing import Optional

class Login(BaseModel):
    username: str
    password: str
    company_id: Optional[int] = None
    store_id: Optional[int] = None

class ContextSwitch(BaseModel):
    company_id: int
    store_id: int

class CompanyCreate(BaseModel):
    name: str = Field(min_length=2, max_length=180)
    legal_name: Optional[str] = Field(default=None, max_length=180)
    document: Optional[str] = Field(default=None, max_length=30)
    slug: Optional[str] = Field(default=None, max_length=80)
    store_name: str = Field(default="Loja Principal", min_length=2, max_length=180)

class CompanyUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=180)
    legal_name: Optional[str] = Field(default=None, max_length=180)
    document: Optional[str] = Field(default=None, max_length=30)

class StoreCreate(BaseModel):
    name: str = Field(min_length=2, max_length=180)
    code: str = Field(min_length=1, max_length=40)
    document: Optional[str] = Field(default=None, max_length=30)

class StoreUpdate(StoreCreate):
    active: bool = True

class RoleCreate(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    code: Optional[str] = Field(default=None, max_length=40)
    description: Optional[str] = Field(default=None, max_length=240)
    permission_codes: list[str] = Field(default_factory=list)

class RoleUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    description: Optional[str] = Field(default=None, max_length=240)
    permission_codes: list[str] = Field(default_factory=list)
    active: bool = True

class TenantUserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=8, max_length=128)
    full_name: Optional[str] = Field(default=None, max_length=180)
    email: Optional[str] = Field(default=None, max_length=180)
    role_code: str
    all_stores: bool = False
    store_ids: list[int] = Field(default_factory=list)

class MembershipUpdate(BaseModel):
    role_code: str
    all_stores: bool = False
    store_ids: list[int] = Field(default_factory=list)
    active: bool = True
    full_name: Optional[str] = Field(default=None, max_length=180)
    email: Optional[str] = Field(default=None, max_length=180)
    new_password: Optional[str] = Field(default=None, min_length=8, max_length=128)

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
