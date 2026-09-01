from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Product, StoreInventory


def scoped_inventory_query(company_id: int, store_id: int):
    return (
        select(Product, StoreInventory)
        .join(StoreInventory, StoreInventory.product_id == Product.id)
        .where(Product.company_id == company_id, StoreInventory.store_id == store_id)
    )


def get_inventory_product(db: Session, product_id: int, company_id: int, store_id: int, for_update: bool = False):
    query = scoped_inventory_query(company_id, store_id).where(Product.id == product_id)
    if for_update:
        query = query.with_for_update()
    return db.execute(query).first()


def product_payload(product: Product, inventory: StoreInventory):
    return {
        "id": product.id,
        "inventory_id": inventory.id,
        "store_id": inventory.store_id,
        "name": product.name,
        "barcode": product.barcode,
        "brand": product.brand,
        "category": product.category,
        "package_content": product.package_content,
        "unit": product.unit,
        "stock": inventory.stock,
        "min_stock": inventory.min_stock,
        "cost": float(inventory.average_cost),
        "price": float(inventory.price),
        "active": product.active and inventory.active,
    }
