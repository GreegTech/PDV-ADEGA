from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Numeric, String, Text, UniqueConstraint, func, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from .database import Base, get_db
from .models import Purchase, Sale, Supplier
from .tenancy import require

router = APIRouter(prefix="/finance", tags=["finance"])
MONEY = Decimal("0.01")


def money(value) -> Decimal:
    return Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP)


class FinancialCategory(Base):
    __tablename__ = "financial_categories"
    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_financial_category_company_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    code: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(120))
    nature: Mapped[str] = mapped_column(String(10), index=True)  # REVENUE | EXPENSE
    dre_group: Mapped[str] = mapped_column(String(40), default="OTHER", index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class FinancialAccount(Base):
    __tablename__ = "financial_accounts"
    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_financial_account_company_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    store_id: Mapped[int | None] = mapped_column(ForeignKey("stores.id"), nullable=True, index=True)
    code: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(120))
    account_type: Mapped[str] = mapped_column(String(20), default="BANK")  # CASH | BANK | WALLET
    opening_balance: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class FinancialEntry(Base):
    __tablename__ = "financial_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    store_id: Mapped[int | None] = mapped_column(ForeignKey("stores.id"), nullable=True, index=True)
    category_id: Mapped[int | None] = mapped_column(ForeignKey("financial_categories.id"), nullable=True, index=True)
    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"), nullable=True, index=True)
    purchase_id: Mapped[int | None] = mapped_column(ForeignKey("purchases.id"), nullable=True, unique=True, index=True)
    sale_id: Mapped[int | None] = mapped_column(ForeignKey("sales.id"), nullable=True, unique=True, index=True)
    kind: Mapped[str] = mapped_column(String(12), index=True)  # PAYABLE | RECEIVABLE
    status: Mapped[str] = mapped_column(String(12), default="OPEN", index=True)
    description: Mapped[str] = mapped_column(String(240))
    document: Mapped[str | None] = mapped_column(String(100), nullable=True)
    issue_date: Mapped[date] = mapped_column(Date, default=date.today, index=True)
    competence_date: Mapped[date] = mapped_column(Date, default=date.today, index=True)
    due_date: Mapped[date] = mapped_column(Date, index=True)
    original_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    settled_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class FinancialSettlement(Base):
    __tablename__ = "financial_settlements"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_id: Mapped[int] = mapped_column(ForeignKey("companies.id"), index=True)
    store_id: Mapped[int | None] = mapped_column(ForeignKey("stores.id"), nullable=True, index=True)
    entry_id: Mapped[int] = mapped_column(ForeignKey("financial_entries.id", ondelete="CASCADE"), index=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("financial_accounts.id"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    payment_method: Mapped[str | None] = mapped_column(String(30), nullable=True)
    settled_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    notes: Mapped[str | None] = mapped_column(String(240), nullable=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)


class CategoryCreate(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=120)
    nature: str
    dre_group: str = "OTHER"


class AccountCreate(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=120)
    account_type: str = "BANK"
    opening_balance: Decimal = Decimal("0")
    store_id: int | None = None


class EntryCreate(BaseModel):
    kind: str
    description: str = Field(min_length=1, max_length=240)
    original_amount: Decimal = Field(gt=0)
    due_date: date
    issue_date: date = Field(default_factory=date.today)
    competence_date: date = Field(default_factory=date.today)
    category_id: int | None = None
    supplier_id: int | None = None
    document: str | None = None
    notes: str | None = None
    store_id: int | None = None


class SettlementCreate(BaseModel):
    account_id: int
    amount: Decimal = Field(gt=0)
    payment_method: str | None = None
    settled_at: datetime = Field(default_factory=datetime.utcnow)
    notes: str | None = None


class SourceEntryCreate(BaseModel):
    due_date: date
    competence_date: date | None = None
    category_id: int | None = None
    account_id: int | None = None
    settle_now: bool = False
    payment_method: str | None = None


def normalize_kind(kind: str) -> str:
    value = kind.strip().upper()
    if value not in {"PAYABLE", "RECEIVABLE"}:
        raise HTTPException(400, "kind deve ser PAYABLE ou RECEIVABLE")
    return value


def validate_category(db: Session, company_id: int, category_id: int | None, kind: str):
    if category_id is None:
        return None
    category = db.scalar(select(FinancialCategory).where(FinancialCategory.id == category_id, FinancialCategory.company_id == company_id, FinancialCategory.active == True))
    if not category:
        raise HTTPException(404, "Categoria financeira não encontrada")
    expected = "EXPENSE" if kind == "PAYABLE" else "REVENUE"
    if category.nature != expected:
        raise HTTPException(400, f"Categoria deve ter natureza {expected}")
    return category


def serialize_entry(entry: FinancialEntry):
    outstanding = money(entry.original_amount) - money(entry.settled_amount)
    return {
        "id": entry.id,
        "store_id": entry.store_id,
        "category_id": entry.category_id,
        "supplier_id": entry.supplier_id,
        "purchase_id": entry.purchase_id,
        "sale_id": entry.sale_id,
        "kind": entry.kind,
        "status": entry.status,
        "description": entry.description,
        "document": entry.document,
        "issue_date": entry.issue_date,
        "competence_date": entry.competence_date,
        "due_date": entry.due_date,
        "original_amount": float(entry.original_amount),
        "settled_amount": float(entry.settled_amount),
        "outstanding_amount": float(max(Decimal("0"), outstanding)),
        "notes": entry.notes,
        "created_at": entry.created_at,
    }


def scoped_entry(db: Session, entry_id: int, company_id: int) -> FinancialEntry:
    entry = db.scalar(select(FinancialEntry).where(FinancialEntry.id == entry_id, FinancialEntry.company_id == company_id))
    if not entry:
        raise HTTPException(404, "Lançamento financeiro não encontrado")
    return entry


def apply_settlement(db: Session, entry: FinancialEntry, data: SettlementCreate, user):
    if entry.status in {"PAID", "CANCELLED"}:
        raise HTTPException(409, f"Lançamento está {entry.status}")
    account = db.scalar(select(FinancialAccount).where(FinancialAccount.id == data.account_id, FinancialAccount.company_id == user.company_id, FinancialAccount.active == True))
    if not account:
        raise HTTPException(404, "Conta financeira não encontrada")
    remaining = money(entry.original_amount) - money(entry.settled_amount)
    amount = money(data.amount)
    if amount > remaining:
        raise HTTPException(400, "Valor da baixa é maior que o saldo em aberto")
    db.add(FinancialSettlement(company_id=user.company_id, store_id=entry.store_id, entry_id=entry.id, account_id=account.id, amount=amount, payment_method=data.payment_method, settled_at=data.settled_at, notes=data.notes, user_id=user.id))
    entry.settled_amount = money(entry.settled_amount) + amount
    entry.status = "PAID" if money(entry.settled_amount) >= money(entry.original_amount) else "PARTIAL"
    return entry


@router.get("/categories")
def list_categories(db: Session = Depends(get_db), user=Depends(require("finance.read"))):
    rows = db.scalars(select(FinancialCategory).where(FinancialCategory.company_id == user.company_id, FinancialCategory.active == True).order_by(FinancialCategory.nature, FinancialCategory.name)).all()
    return [{"id": row.id, "code": row.code, "name": row.name, "nature": row.nature, "dre_group": row.dre_group} for row in rows]


@router.post("/categories")
def create_category(data: CategoryCreate, db: Session = Depends(get_db), user=Depends(require("finance.write"))):
    nature = data.nature.strip().upper()
    if nature not in {"REVENUE", "EXPENSE"}:
        raise HTTPException(400, "nature deve ser REVENUE ou EXPENSE")
    row = FinancialCategory(company_id=user.company_id, code=data.code.strip().upper(), name=data.name.strip(), nature=nature, dre_group=data.dre_group.strip().upper())
    db.add(row)
    try:
        db.commit(); db.refresh(row)
    except Exception:
        db.rollback(); raise HTTPException(409, "Código de categoria já cadastrado")
    return {"id": row.id, "code": row.code, "name": row.name, "nature": row.nature, "dre_group": row.dre_group}


@router.get("/accounts")
def list_accounts(db: Session = Depends(get_db), user=Depends(require("finance.read"))):
    rows = db.scalars(select(FinancialAccount).where(FinancialAccount.company_id == user.company_id, FinancialAccount.active == True).order_by(FinancialAccount.name)).all()
    return [{"id": row.id, "store_id": row.store_id, "code": row.code, "name": row.name, "account_type": row.account_type, "opening_balance": float(row.opening_balance)} for row in rows]


@router.post("/accounts")
def create_account(data: AccountCreate, db: Session = Depends(get_db), user=Depends(require("finance.write"))):
    store_id = data.store_id if data.store_id is not None else user.store_id
    row = FinancialAccount(company_id=user.company_id, store_id=store_id, code=data.code.strip().upper(), name=data.name.strip(), account_type=data.account_type.strip().upper(), opening_balance=money(data.opening_balance))
    db.add(row)
    try:
        db.commit(); db.refresh(row)
    except Exception:
        db.rollback(); raise HTTPException(409, "Código de conta financeira já cadastrado")
    return {"id": row.id, "store_id": row.store_id, "code": row.code, "name": row.name, "account_type": row.account_type, "opening_balance": float(row.opening_balance)}


@router.post("/entries")
def create_entry(data: EntryCreate, db: Session = Depends(get_db), user=Depends(require("finance.write"))):
    kind = normalize_kind(data.kind)
    validate_category(db, user.company_id, data.category_id, kind)
    if data.supplier_id and not db.scalar(select(Supplier.id).where(Supplier.id == data.supplier_id, Supplier.company_id == user.company_id)):
        raise HTTPException(404, "Fornecedor não encontrado")
    entry = FinancialEntry(company_id=user.company_id, store_id=data.store_id if data.store_id is not None else user.store_id, category_id=data.category_id, supplier_id=data.supplier_id, kind=kind, status="OPEN", description=data.description.strip(), document=data.document, issue_date=data.issue_date, competence_date=data.competence_date, due_date=data.due_date, original_amount=money(data.original_amount), settled_amount=0, notes=data.notes, created_by=user.id)
    db.add(entry); db.commit(); db.refresh(entry)
    return serialize_entry(entry)


@router.get("/entries")
def list_entries(kind: str | None = None, status: str | None = None, due_from: date | None = None, due_to: date | None = None, store_id: int | None = None, db: Session = Depends(get_db), user=Depends(require("finance.read"))):
    query = select(FinancialEntry).where(FinancialEntry.company_id == user.company_id)
    if kind: query = query.where(FinancialEntry.kind == normalize_kind(kind))
    if status: query = query.where(FinancialEntry.status == status.strip().upper())
    if due_from: query = query.where(FinancialEntry.due_date >= due_from)
    if due_to: query = query.where(FinancialEntry.due_date <= due_to)
    if store_id is not None: query = query.where(FinancialEntry.store_id == store_id)
    rows = db.scalars(query.order_by(FinancialEntry.due_date, FinancialEntry.id)).all()
    return [serialize_entry(row) for row in rows]


@router.post("/entries/{entry_id}/settle")
def settle_entry(entry_id: int, data: SettlementCreate, db: Session = Depends(get_db), user=Depends(require("finance.settle"))):
    entry = scoped_entry(db, entry_id, user.company_id)
    apply_settlement(db, entry, data, user)
    db.commit(); db.refresh(entry)
    return serialize_entry(entry)


@router.post("/entries/{entry_id}/cancel")
def cancel_entry(entry_id: int, db: Session = Depends(get_db), user=Depends(require("finance.write"))):
    entry = scoped_entry(db, entry_id, user.company_id)
    if money(entry.settled_amount) > 0:
        raise HTTPException(409, "Não é possível cancelar lançamento com baixa. Estorne a baixa primeiro.")
    entry.status = "CANCELLED"; db.commit(); db.refresh(entry)
    return serialize_entry(entry)


@router.post("/payables/from-purchase/{purchase_id}")
def payable_from_purchase(purchase_id: int, data: SourceEntryCreate, db: Session = Depends(get_db), user=Depends(require("finance.write"))):
    purchase = db.scalar(select(Purchase).where(Purchase.id == purchase_id, Purchase.company_id == user.company_id))
    if not purchase: raise HTTPException(404, "Compra não encontrada")
    existing = db.scalar(select(FinancialEntry).where(FinancialEntry.purchase_id == purchase.id))
    if existing: return serialize_entry(existing)
    validate_category(db, user.company_id, data.category_id, "PAYABLE")
    supplier = db.get(Supplier, purchase.supplier_id)
    entry = FinancialEntry(company_id=user.company_id, store_id=purchase.store_id, category_id=data.category_id, supplier_id=purchase.supplier_id, purchase_id=purchase.id, kind="PAYABLE", status="OPEN", description=f"Compra #{purchase.id} - {supplier.name if supplier else 'Fornecedor'}", document=purchase.document, issue_date=purchase.created_at.date(), competence_date=data.competence_date or purchase.created_at.date(), due_date=data.due_date, original_amount=money(purchase.total), settled_amount=0, created_by=user.id)
    db.add(entry); db.flush()
    if data.settle_now:
        if not data.account_id: raise HTTPException(400, "account_id é obrigatório quando settle_now=true")
        apply_settlement(db, entry, SettlementCreate(account_id=data.account_id, amount=money(entry.original_amount), payment_method=data.payment_method), user)
    db.commit(); db.refresh(entry)
    return serialize_entry(entry)


@router.post("/receivables/from-sale/{sale_id}")
def receivable_from_sale(sale_id: int, data: SourceEntryCreate, db: Session = Depends(get_db), user=Depends(require("finance.write"))):
    sale = db.scalar(select(Sale).where(Sale.id == sale_id, Sale.company_id == user.company_id))
    if not sale: raise HTTPException(404, "Venda não encontrada")
    existing = db.scalar(select(FinancialEntry).where(FinancialEntry.sale_id == sale.id))
    if existing: return serialize_entry(existing)
    validate_category(db, user.company_id, data.category_id, "RECEIVABLE")
    entry = FinancialEntry(company_id=user.company_id, store_id=sale.store_id, category_id=data.category_id, sale_id=sale.id, kind="RECEIVABLE", status="OPEN", description=f"Venda #{sale.id}", document=f"VENDA:{sale.id}", issue_date=sale.created_at.date(), competence_date=data.competence_date or sale.created_at.date(), due_date=data.due_date, original_amount=money(sale.total), settled_amount=0, created_by=user.id)
    db.add(entry); db.flush()
    if data.settle_now:
        if not data.account_id: raise HTTPException(400, "account_id é obrigatório quando settle_now=true")
        apply_settlement(db, entry, SettlementCreate(account_id=data.account_id, amount=money(entry.original_amount), payment_method=data.payment_method), user)
    db.commit(); db.refresh(entry)
    return serialize_entry(entry)


@router.get("/summary")
def finance_summary(db: Session = Depends(get_db), user=Depends(require("finance.read"))):
    open_payables = db.scalar(select(func.coalesce(func.sum(FinancialEntry.original_amount - FinancialEntry.settled_amount), 0)).where(FinancialEntry.company_id == user.company_id, FinancialEntry.kind == "PAYABLE", FinancialEntry.status.in_(["OPEN", "PARTIAL"]))) or 0
    open_receivables = db.scalar(select(func.coalesce(func.sum(FinancialEntry.original_amount - FinancialEntry.settled_amount), 0)).where(FinancialEntry.company_id == user.company_id, FinancialEntry.kind == "RECEIVABLE", FinancialEntry.status.in_(["OPEN", "PARTIAL"]))) or 0
    overdue_payables = db.scalar(select(func.coalesce(func.sum(FinancialEntry.original_amount - FinancialEntry.settled_amount), 0)).where(FinancialEntry.company_id == user.company_id, FinancialEntry.kind == "PAYABLE", FinancialEntry.status.in_(["OPEN", "PARTIAL"]), FinancialEntry.due_date < date.today())) or 0
    overdue_receivables = db.scalar(select(func.coalesce(func.sum(FinancialEntry.original_amount - FinancialEntry.settled_amount), 0)).where(FinancialEntry.company_id == user.company_id, FinancialEntry.kind == "RECEIVABLE", FinancialEntry.status.in_(["OPEN", "PARTIAL"]), FinancialEntry.due_date < date.today())) or 0
    return {"open_payables": float(open_payables), "open_receivables": float(open_receivables), "net_open_position": float(money(open_receivables) - money(open_payables)), "overdue_payables": float(overdue_payables), "overdue_receivables": float(overdue_receivables)}


@router.get("/cash-flow")
def cash_flow(start: date, end: date, db: Session = Depends(get_db), user=Depends(require("finance.reports"))):
    if end < start: raise HTTPException(400, "end deve ser maior ou igual a start")
    settlements = db.execute(select(FinancialSettlement.settled_at, FinancialSettlement.amount, FinancialEntry.kind).join(FinancialEntry, FinancialEntry.id == FinancialSettlement.entry_id).where(FinancialSettlement.company_id == user.company_id, func.date(FinancialSettlement.settled_at) >= start, func.date(FinancialSettlement.settled_at) <= end).order_by(FinancialSettlement.settled_at)).all()
    forecast = db.scalars(select(FinancialEntry).where(FinancialEntry.company_id == user.company_id, FinancialEntry.status.in_(["OPEN", "PARTIAL"]), FinancialEntry.due_date >= start, FinancialEntry.due_date <= end).order_by(FinancialEntry.due_date)).all()
    realized_in = sum((money(amount) for _, amount, kind in settlements if kind == "RECEIVABLE"), Decimal("0"))
    realized_out = sum((money(amount) for _, amount, kind in settlements if kind == "PAYABLE"), Decimal("0"))
    forecast_in = sum((money(row.original_amount) - money(row.settled_amount) for row in forecast if row.kind == "RECEIVABLE"), Decimal("0"))
    forecast_out = sum((money(row.original_amount) - money(row.settled_amount) for row in forecast if row.kind == "PAYABLE"), Decimal("0"))
    return {"start": start, "end": end, "realized": {"in": float(realized_in), "out": float(realized_out), "net": float(realized_in - realized_out)}, "forecast": {"in": float(forecast_in), "out": float(forecast_out), "net": float(forecast_in - forecast_out)}, "projected_net": float((realized_in - realized_out) + (forecast_in - forecast_out))}


@router.get("/dre")
def dre(start: date, end: date, db: Session = Depends(get_db), user=Depends(require("finance.reports"))):
    if end < start: raise HTTPException(400, "end deve ser maior ou igual a start")
    sales_row = db.execute(select(func.coalesce(func.sum(Sale.total), 0), func.coalesce(func.sum(Sale.discount_total), 0), func.coalesce(func.sum(Sale.cmv_total), 0)).where(Sale.company_id == user.company_id, func.date(Sale.created_at) >= start, func.date(Sale.created_at) <= end)).one()
    net_sales, discounts, cmv = map(money, sales_row)
    manual_revenues = db.scalar(select(func.coalesce(func.sum(FinancialEntry.original_amount), 0)).join(FinancialCategory, FinancialCategory.id == FinancialEntry.category_id).where(FinancialEntry.company_id == user.company_id, FinancialEntry.kind == "RECEIVABLE", FinancialEntry.sale_id.is_(None), FinancialEntry.status != "CANCELLED", FinancialEntry.competence_date >= start, FinancialEntry.competence_date <= end, FinancialCategory.dre_group != "NON_OPERATING")) or 0
    manual_expenses = db.scalar(select(func.coalesce(func.sum(FinancialEntry.original_amount), 0)).join(FinancialCategory, FinancialCategory.id == FinancialEntry.category_id).where(FinancialEntry.company_id == user.company_id, FinancialEntry.kind == "PAYABLE", FinancialEntry.purchase_id.is_(None), FinancialEntry.status != "CANCELLED", FinancialEntry.competence_date >= start, FinancialEntry.competence_date <= end, FinancialCategory.dre_group != "NON_OPERATING")) or 0
    manual_revenues = money(manual_revenues); manual_expenses = money(manual_expenses)
    gross_profit = net_sales - cmv
    operating_result = gross_profit + manual_revenues - manual_expenses
    return {"start": start, "end": end, "gross_sales_before_discount": float(net_sales + discounts), "sales_discounts": float(discounts), "net_sales": float(net_sales), "cmv": float(cmv), "gross_profit": float(gross_profit), "other_operating_revenues": float(manual_revenues), "operating_expenses": float(manual_expenses), "operating_result": float(operating_result), "gross_margin_percent": float(money((gross_profit / net_sales) * 100)) if net_sales else 0.0}
