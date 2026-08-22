from pydantic import BaseModel, Field
from typing import Optional

class NfeProductCreate(BaseModel):
    line: int
    barcode: Optional[str] = None
    name: str = Field(min_length=2, max_length=180)
    brand: Optional[str] = None
    category: str = "Outros"
    package_content: Optional[str] = None
    unit: str = "UN"
    quantity: int = Field(gt=0)
    unit_cost: float = Field(gt=0)
    price: float = Field(ge=0)
    min_stock: int = Field(default=0, ge=0)

class NfeReconcileRequest(BaseModel):
    supplier_id: int
    document: str = Field(min_length=1, max_length=80)
    products: list[NfeProductCreate]
