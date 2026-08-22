from datetime import datetime
from sqlalchemy import String, Integer, Numeric, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(30), default="admin")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(180), index=True)
    barcode: Mapped[str | None] = mapped_column(String(80), unique=True, nullable=True)
    brand: Mapped[str | None] = mapped_column(String(120), nullable=True)
    category: Mapped[str] = mapped_column(String(80), default="Outros")
    package_content: Mapped[str | None] = mapped_column(String(60), nullable=True)
    unit: Mapped[str] = mapped_column(String(20), default="UN")
    stock: Mapped[int] = mapped_column(Integer, default=0)
    min_stock: Mapped[int] = mapped_column(Integer, default=0)
    cost: Mapped[float] = mapped_column(Numeric(12,2), default=0)
    price: Mapped[float] = mapped_column(Numeric(12,2), default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class CatalogProduct(Base):
    __tablename__ = "catalog_products"
    id: Mapped[int] = mapped_column(primary_key=True)
    barcode: Mapped[str] = mapped_column(String(14), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(240), index=True)
    brand: Mapped[str | None] = mapped_column(String(120), nullable=True)
    category: Mapped[str] = mapped_column(String(100), default="Outros")
    package_content: Mapped[str | None] = mapped_column(String(60), nullable=True)
    unit: Mapped[str] = mapped_column(String(20), default="UN")
    source: Mapped[str | None] = mapped_column(String(500), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Sale(Base):
    __tablename__ = "sales"
    id: Mapped[int] = mapped_column(primary_key=True)
    total: Mapped[float] = mapped_column(Numeric(12,2))
    payment_method: Mapped[str] = mapped_column(String(30))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    items: Mapped[list["SaleItem"]] = relationship(cascade="all, delete-orphan")

class SaleItem(Base):
    __tablename__ = "sale_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    sale_id: Mapped[int] = mapped_column(ForeignKey("sales.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[float] = mapped_column(Numeric(12,2))
    unit_cost: Mapped[float] = mapped_column(Numeric(12,2))

class StockMovement(Base):
    __tablename__ = "stock_movements"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    type: Mapped[str] = mapped_column(String(30))
    quantity: Mapped[int] = mapped_column(Integer)
    reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
