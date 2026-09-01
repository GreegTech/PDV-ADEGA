from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .cash import get_open_cash_session
from .database import get_db
from .inventory import get_inventory_product
from .models import (
    CashMovement,
    CashRegister,
    CashSession,
    InventoryTransfer,
    InventoryTransferItem,
    Product,
    Store,
    StoreInventory,
    StockMovement,
    User,
)
from .schemas import CashClose, CashMovementCreate, CashOpen, CashRegisterCreate, InventoryTransferCreate
from .tenancy import require

router = APIRouter()
CENT = Decimal("0.01")


def amount(value):
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def session_payload(db: Session, session: CashSession):
    rows = db.execute(
        select(CashMovement.payment_method, func.coalesce(func.sum(CashMovement.amount), 0))
        .where(CashMovement.session_id == session.id, CashMovement.type == "SALE")
        .group_by(CashMovement.payment_method)
    ).all()
    return {
        "id": session.id,
        "register_id": session.register_id,
        "user_id": session.user_id,
        "status": session.status,
        "opening_amount": float(session.opening_amount),
        "expected_cash": float(session.expected_cash),
        "closing_amount": float(session.closing_amount) if session.closing_amount is not None else None,
        "difference": float(session.difference) if session.difference is not None else None,
        "opened_at": session.opened_at,
        "closed_at": session.closed_at,
        "sales_by_payment": {method or "OUTRO": float(total) for method, total in rows},
    }


@router.get("/stock/availability/{product_id}")
def stock_availability(product_id: int, db: Session = Depends(get_db), context=Depends(require("inventory.read"))):
    product = db.scalar(select(Product).where(Product.id == product_id, Product.company_id == context.company_id))
    if not product:
        raise HTTPException(404, "Produto não encontrado")
    rows = db.execute(
        select(StoreInventory, Store.name, Store.code)
        .join(Store, Store.id == StoreInventory.store_id)
        .where(StoreInventory.company_id == context.company_id, StoreInventory.product_id == product_id, Store.active == True)
        .order_by(Store.name)
    ).all()
    return {
        "product_id": product.id,
        "product": product.name,
        "stores": [
            {"store_id": inventory.store_id, "store": name, "code": code, "stock": inventory.stock, "min_stock": inventory.min_stock, "average_cost": float(inventory.average_cost), "price": float(inventory.price), "active": inventory.active}
            for inventory, name, code in rows
        ],
    }


@router.get("/stock/transfer-destinations")
def transfer_destinations(db: Session = Depends(get_db), context=Depends(require("inventory.transfer"))):
    stores = db.scalars(
        select(Store)
        .where(
            Store.company_id == context.company_id,
            Store.id != context.store_id,
            Store.active == True,
        )
        .order_by(Store.name)
    ).all()
    return [{"id": store.id, "name": store.name, "code": store.code, "active": store.active} for store in stores]


@router.post("/stock/transfers")
def create_transfer(data: InventoryTransferCreate, db: Session = Depends(get_db), context=Depends(require("inventory.transfer"))):
    if not data.items:
        raise HTTPException(400, "Transferência sem itens")
    if data.destination_store_id == context.store_id:
        raise HTTPException(400, "A loja de destino deve ser diferente da origem")
    destination = db.scalar(select(Store).where(Store.id == data.destination_store_id, Store.company_id == context.company_id, Store.active == True))
    if not destination:
        raise HTTPException(404, "Loja de destino não encontrada")
    quantities = {}
    for line in data.items:
        quantities[line.product_id] = quantities.get(line.product_id, 0) + line.quantity

    try:
        transfer = InventoryTransfer(
            company_id=context.company_id,
            source_store_id=context.store_id,
            destination_store_id=destination.id,
            status="COMPLETED",
            notes=data.notes,
            user_id=context.id,
        )
        db.add(transfer)
        db.flush()
        for product_id in sorted(quantities):
            quantity = quantities[product_id]
            source_row = get_inventory_product(db, product_id, context.company_id, context.store_id, for_update=True)
            if not source_row:
                raise HTTPException(404, f"Produto {product_id} não encontrado na loja de origem")
            product, source = source_row
            if source.stock < quantity:
                raise HTTPException(400, f"Estoque insuficiente para transferir: {product.name}")
            destination_inventory = db.scalar(
                select(StoreInventory)
                .where(StoreInventory.store_id == destination.id, StoreInventory.product_id == product.id)
                .with_for_update()
            )
            if not destination_inventory:
                destination_inventory = StoreInventory(
                    company_id=context.company_id,
                    store_id=destination.id,
                    product_id=product.id,
                    stock=0,
                    min_stock=0,
                    average_cost=source.average_cost,
                    price=source.price,
                    active=True,
                )
                db.add(destination_inventory)
                db.flush()
            source_before = source.stock
            destination_before = destination_inventory.stock
            unit_cost = amount(source.average_cost)
            destination_after = destination_before + quantity
            destination_inventory.average_cost = amount(
                ((amount(destination_inventory.average_cost) * destination_before) + (unit_cost * quantity)) / destination_after
            )
            source.stock -= quantity
            destination_inventory.stock = destination_after
            db.add(
                InventoryTransferItem(
                    transfer_id=transfer.id,
                    product_id=product.id,
                    quantity=quantity,
                    unit_cost=unit_cost,
                    source_stock_before=source_before,
                    source_stock_after=source.stock,
                    destination_stock_before=destination_before,
                    destination_stock_after=destination_after,
                )
            )
            db.add_all([
                StockMovement(company_id=context.company_id, store_id=context.store_id, product_id=product.id, type="TRANSFERENCIA_SAIDA", quantity=-quantity, reference=f"TRANSFERENCIA:{transfer.id};DESTINO:{destination.id}", user_id=context.id),
                StockMovement(company_id=context.company_id, store_id=destination.id, product_id=product.id, type="TRANSFERENCIA_ENTRADA", quantity=quantity, reference=f"TRANSFERENCIA:{transfer.id};ORIGEM:{context.store_id}", user_id=context.id),
            ])
        db.commit()
        return {"id": transfer.id, "status": transfer.status, "source_store_id": transfer.source_store_id, "destination_store_id": transfer.destination_store_id, "items": len(quantities)}
    except Exception:
        db.rollback()
        raise


@router.get("/stock/transfers")
def list_transfers(limit: int = 100, db: Session = Depends(get_db), context=Depends(require("inventory.read"))):
    limit = max(1, min(limit, 500))
    rows = db.execute(
        select(InventoryTransfer, User.username)
        .join(User, User.id == InventoryTransfer.user_id)
        .where(
            InventoryTransfer.company_id == context.company_id,
            (InventoryTransfer.source_store_id == context.store_id) | (InventoryTransfer.destination_store_id == context.store_id),
        )
        .order_by(InventoryTransfer.created_at.desc(), InventoryTransfer.id.desc())
        .limit(limit)
    ).all()
    return [{"id": transfer.id, "source_store_id": transfer.source_store_id, "destination_store_id": transfer.destination_store_id, "status": transfer.status, "notes": transfer.notes, "user": username, "created_at": transfer.created_at} for transfer, username in rows]


@router.get("/cash/registers")
def list_registers(db: Session = Depends(get_db), context=Depends(require("cash.read"))):
    rows = db.scalars(select(CashRegister).where(CashRegister.company_id == context.company_id, CashRegister.store_id == context.store_id, CashRegister.active == True).order_by(CashRegister.name)).all()
    return [{"id": register.id, "name": register.name, "code": register.code, "active": register.active} for register in rows]


@router.post("/cash/registers")
def create_register(data: CashRegisterCreate, db: Session = Depends(get_db), context=Depends(require("stores.manage"))):
    register = CashRegister(company_id=context.company_id, store_id=context.store_id, name=data.name.strip(), code=data.code.strip().upper())
    try:
        db.add(register)
        db.commit()
        db.refresh(register)
        return {"id": register.id, "name": register.name, "code": register.code, "active": register.active}
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Código de caixa já utilizado nesta loja")


@router.get("/cash/current")
def current_cash(db: Session = Depends(get_db), context=Depends(require("cash.read"))):
    session = get_open_cash_session(db, context.company_id, context.store_id, context.id)
    return session_payload(db, session) if session else None


@router.post("/cash/open")
def open_cash(data: CashOpen, db: Session = Depends(get_db), context=Depends(require("cash.operate"))):
    register = db.scalar(select(CashRegister).where(CashRegister.id == data.register_id, CashRegister.company_id == context.company_id, CashRegister.store_id == context.store_id, CashRegister.active == True))
    if not register:
        raise HTTPException(404, "Caixa não encontrado")
    if get_open_cash_session(db, context.company_id, context.store_id, context.id):
        raise HTTPException(409, "O usuário já possui um caixa aberto nesta loja")
    if db.scalar(select(CashSession.id).where(CashSession.register_id == register.id, CashSession.status == "OPEN")):
        raise HTTPException(409, "Este caixa já está aberto por outro operador")
    opening = amount(data.opening_amount)
    try:
        session = CashSession(company_id=context.company_id, store_id=context.store_id, register_id=register.id, user_id=context.id, status="OPEN", opening_amount=opening, expected_cash=opening)
        db.add(session)
        db.flush()
        db.add(CashMovement(company_id=context.company_id, store_id=context.store_id, session_id=session.id, type="OPENING", amount=opening, payment_method="Dinheiro", reference=f"CAIXA:{session.id}", user_id=context.id))
        db.commit()
        db.refresh(session)
        return session_payload(db, session)
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "O usuário ou terminal já possui um caixa aberto")


@router.post("/cash/movements")
def cash_adjustment(data: CashMovementCreate, db: Session = Depends(get_db), context=Depends(require("cash.adjust"))):
    kind = data.type.strip().upper()
    if kind not in {"SUPPLY", "WITHDRAWAL"}:
        raise HTTPException(400, "Movimento deve ser SUPPLY ou WITHDRAWAL")
    session = get_open_cash_session(db, context.company_id, context.store_id, context.id, for_update=True)
    if not session:
        raise HTTPException(409, "Abra o caixa antes de movimentar valores")
    value = amount(data.amount)
    if kind == "WITHDRAWAL" and value > session.expected_cash:
        raise HTTPException(400, "Sangria maior que o dinheiro esperado em caixa")
    session.expected_cash += value if kind == "SUPPLY" else -value
    movement = CashMovement(company_id=context.company_id, store_id=context.store_id, session_id=session.id, type=kind, amount=value, payment_method="Dinheiro", reference=f"CAIXA:{session.id}", notes=data.notes, user_id=context.id)
    db.add(movement)
    db.commit()
    return {"id": movement.id, "type": kind, "amount": float(value), "expected_cash": float(session.expected_cash)}


@router.post("/cash/close")
def close_cash(data: CashClose, db: Session = Depends(get_db), context=Depends(require("cash.operate"))):
    session = get_open_cash_session(db, context.company_id, context.store_id, context.id, for_update=True)
    if not session:
        raise HTTPException(409, "Nenhum caixa aberto para este usuário")
    closing = amount(data.closing_amount)
    session.closing_amount = closing
    session.difference = amount(closing - amount(session.expected_cash))
    session.status = "CLOSED"
    session.closed_at = datetime.utcnow()
    db.add(CashMovement(company_id=context.company_id, store_id=context.store_id, session_id=session.id, type="CLOSING", amount=closing, payment_method="Dinheiro", reference=f"CAIXA:{session.id}", user_id=context.id))
    db.commit()
    return session_payload(db, session)


@router.get("/cash/sessions")
def list_cash_sessions(limit: int = 100, db: Session = Depends(get_db), context=Depends(require("cash.read"))):
    limit = max(1, min(limit, 500))
    sessions = db.scalars(select(CashSession).where(CashSession.company_id == context.company_id, CashSession.store_id == context.store_id).order_by(CashSession.opened_at.desc()).limit(limit)).all()
    return [session_payload(db, session) for session in sessions]
