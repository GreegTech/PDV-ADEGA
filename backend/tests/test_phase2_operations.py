from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.cash import record_sale
from app.database import Base
from app.models import (
    CashMovement,
    CashRegister,
    CashSession,
    Company,
    Product,
    Sale,
    Store,
    StoreInventory,
    StockMovement,
    User,
)
from app.operations import close_cash, create_transfer, open_cash
from app.schemas import CashClose, CashOpen, InventoryTransferCreate, InventoryTransferLine


@pytest.fixture()
def phase2():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        company = Company(name="Adega", slug="adega")
        user = User(username="admin", password_hash="hash", role="admin")
        db.add_all([company, user])
        db.flush()
        source = Store(company_id=company.id, name="Matriz", code="MATRIZ")
        destination = Store(company_id=company.id, name="Filial", code="FILIAL")
        db.add_all([source, destination])
        db.flush()
        product = Product(company_id=company.id, name="Produto", barcode="7894900010015", cost=4, price=8)
        db.add(product)
        db.flush()
        inventory = StoreInventory(company_id=company.id, store_id=source.id, product_id=product.id, stock=10, min_stock=2, average_cost=4, price=8)
        register = CashRegister(company_id=company.id, store_id=source.id, name="Principal", code="CX-01")
        db.add_all([inventory, register])
        db.commit()
        context = SimpleNamespace(company_id=company.id, store_id=source.id, id=user.id)
        yield db, context, product, source, destination, register
    engine.dispose()


def test_transfer_moves_stock_and_creates_destination_inventory(phase2):
    db, context, product, source, destination, _ = phase2
    result = create_transfer(
        InventoryTransferCreate(destination_store_id=destination.id, items=[InventoryTransferLine(product_id=product.id, quantity=3)]),
        db,
        context,
    )
    assert result["status"] == "COMPLETED"
    source_inventory = db.scalar(select(StoreInventory).where(StoreInventory.store_id == source.id, StoreInventory.product_id == product.id))
    destination_inventory = db.scalar(select(StoreInventory).where(StoreInventory.store_id == destination.id, StoreInventory.product_id == product.id))
    assert source_inventory.stock == 7
    assert destination_inventory.stock == 3
    assert destination_inventory.average_cost == 4
    assert db.scalar(select(func.count(StockMovement.id))) == 2


def test_transfer_is_atomic_when_stock_is_insufficient(phase2):
    db, context, product, source, destination, _ = phase2
    with pytest.raises(HTTPException) as exc:
        create_transfer(
            InventoryTransferCreate(destination_store_id=destination.id, items=[InventoryTransferLine(product_id=product.id, quantity=11)]),
            db,
            context,
        )
    assert exc.value.status_code == 400
    assert db.scalar(select(StoreInventory.stock).where(StoreInventory.store_id == source.id, StoreInventory.product_id == product.id)) == 10
    assert db.scalar(select(StoreInventory.id).where(StoreInventory.store_id == destination.id, StoreInventory.product_id == product.id)) is None


def test_cash_session_tracks_cash_sales_and_closing_difference(phase2):
    db, context, _, _, _, register = phase2
    opened = open_cash(CashOpen(register_id=register.id, opening_amount=100), db, context)
    session = db.get(CashSession, opened["id"])
    sale = Sale(company_id=context.company_id, store_id=context.store_id, cash_session_id=session.id, total=25, gross_total=25, discount_total=0, cmv_total=10, gross_margin=15, payment_method="Dinheiro", user_id=context.id)
    db.add(sale)
    db.flush()
    record_sale(db, session, sale, context.id)
    db.commit()
    assert session.expected_cash == 125
    assert db.scalar(select(func.count(CashMovement.id)).where(CashMovement.session_id == session.id)) == 2

    closed = close_cash(CashClose(closing_amount=123), db, context)
    assert closed["status"] == "CLOSED"
    assert closed["difference"] == -2


def test_non_cash_sale_does_not_change_drawer_expected_value(phase2):
    db, context, _, _, _, register = phase2
    opened = open_cash(CashOpen(register_id=register.id, opening_amount=50), db, context)
    session = db.get(CashSession, opened["id"])
    sale = Sale(company_id=context.company_id, store_id=context.store_id, cash_session_id=session.id, total=30, gross_total=30, discount_total=0, cmv_total=12, gross_margin=18, payment_method="PIX", user_id=context.id)
    db.add(sale)
    db.flush()
    record_sale(db, session, sale, context.id)
    db.commit()
    assert session.expected_cash == 50
