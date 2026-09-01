from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func, delete as sql_delete
from sqlalchemy.orm import Session

from .database import get_db
from .models import StoreInventory, ProductPriceHistory, Purchase, PurchaseItem, Sale, SaleItem, StockMovement
from .tenancy import require
from .inventory import get_inventory_product

router = APIRouter()


@router.delete('/admin/test-products/{product_id}')
def purge_test_product(product_id: int, db: Session = Depends(get_db), user=Depends(require("companies.manage"))):
    if user.role != 'admin':
        raise HTTPException(403, 'Apenas administradores podem excluir dados de teste definitivamente')

    row = get_inventory_product(db, product_id, user.company_id, user.store_id)
    if not row:
        raise HTTPException(404, 'Produto não encontrado')
    product, inventory = row
    if inventory.active:
        raise HTTPException(409, 'Desative o produto antes de excluir os dados de teste')

    sales_count = db.scalar(select(func.count(SaleItem.id)).join(Sale, Sale.id == SaleItem.sale_id).where(SaleItem.product_id == product_id, Sale.store_id == user.store_id)) or 0
    if sales_count:
        raise HTTPException(409, 'Produto já possui venda e não pode ser apagado, mesmo como dado de teste')

    purchase_items = db.scalars(select(PurchaseItem).join(Purchase, Purchase.id == PurchaseItem.purchase_id).where(PurchaseItem.product_id == product_id, Purchase.store_id == user.store_id)).all()
    purchase_ids = sorted({item.purchase_id for item in purchase_items})
    removed_purchase_items = len(purchase_items)
    removed_movements = db.scalar(select(func.count(StockMovement.id)).where(StockMovement.product_id == product_id, StockMovement.store_id == user.store_id)) or 0

    try:
        db.execute(sql_delete(ProductPriceHistory).where(ProductPriceHistory.product_id == product_id, ProductPriceHistory.store_id == user.store_id))
        db.execute(sql_delete(StockMovement).where(StockMovement.product_id == product_id, StockMovement.store_id == user.store_id))
        if purchase_ids:
            db.execute(sql_delete(PurchaseItem).where(PurchaseItem.product_id == product_id, PurchaseItem.purchase_id.in_(purchase_ids)))
        db.flush()

        removed_purchases = 0
        updated_purchases = 0
        for purchase_id in purchase_ids:
            purchase = db.scalar(select(Purchase).where(Purchase.id == purchase_id, Purchase.company_id == user.company_id, Purchase.store_id == user.store_id))
            if not purchase:
                continue
            remaining_count = db.scalar(select(func.count(PurchaseItem.id)).where(PurchaseItem.purchase_id == purchase_id)) or 0
            if remaining_count == 0:
                db.delete(purchase)
                removed_purchases += 1
            else:
                remaining_total = db.scalar(select(func.coalesce(func.sum(PurchaseItem.total_cost), 0)).where(PurchaseItem.purchase_id == purchase_id)) or 0
                purchase.total = remaining_total
                updated_purchases += 1

        db.delete(inventory)
        db.flush()
        if not db.scalar(select(StoreInventory.id).where(StoreInventory.product_id == product_id)):
            db.delete(product)
        db.commit()
        return {
            'ok': True,
            'product_id': product_id,
            'product': product.name,
            'removed_purchase_items': removed_purchase_items,
            'removed_stock_movements': int(removed_movements),
            'removed_purchases': removed_purchases,
            'updated_purchases': updated_purchases,
        }
    except Exception:
        db.rollback()
        raise
