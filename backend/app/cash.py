import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import CashMovement, CashSession, Sale


def _payment_key(value: str) -> str:
    return unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode().strip().upper()


def is_physical_cash(payment_method: str) -> bool:
    return _payment_key(payment_method) in {"DINHEIRO", "CASH"}


def get_open_cash_session(db: Session, company_id: int, store_id: int, user_id: int, for_update: bool = False):
    query = select(CashSession).where(
        CashSession.company_id == company_id,
        CashSession.store_id == store_id,
        CashSession.user_id == user_id,
        CashSession.status == "OPEN",
    )
    if for_update:
        query = query.with_for_update()
    return db.scalar(query.order_by(CashSession.opened_at.desc(), CashSession.id.desc()))


def record_sale(db: Session, session: CashSession, sale: Sale, user_id: int):
    db.add(
        CashMovement(
            company_id=session.company_id,
            store_id=session.store_id,
            session_id=session.id,
            type="SALE",
            amount=sale.total,
            payment_method=sale.payment_method,
            reference=f"VENDA:{sale.id}",
            user_id=user_id,
        )
    )
    if is_physical_cash(sale.payment_method):
        session.expected_cash += sale.total
