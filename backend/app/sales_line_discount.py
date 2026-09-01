from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from .database import get_db
from .main import discount_limit_for_role, money
from .models import Sale, SaleItem, StockMovement
from .schemas import SaleCreate
from .tenancy import require
from .inventory import get_inventory_product
from .cash import get_open_cash_session, record_sale

router = APIRouter()


@router.post("/sales")
def create_sale_line_discount(
    data: SaleCreate,
    db: Session = Depends(get_db),
    user=Depends(require("sales.create")),
):
    if not data.items:
        raise HTTPException(400, "Venda sem itens")

    gross = Decimal("0")
    discounts = Decimal("0")
    net = Decimal("0")
    cmv = Decimal("0")
    prepared = []
    limit = discount_limit_for_role(user.role)

    try:
        cash_session = get_open_cash_session(db, user.company_id, user.store_id, user.id, for_update=True)
        if not cash_session:
            raise HTTPException(409, "Abra o caixa antes de realizar vendas")
        for line in data.items:
            row = get_inventory_product(db, line.product_id, user.company_id, user.store_id, for_update=True)
            if not row:
                raise HTTPException(404, f"Produto {line.product_id} não encontrado")
            p, inventory = row
            if not p.active or not inventory.active:
                raise HTTPException(400, f"Produto desativado e indisponível para venda: {p.name}")
            if inventory.stock < line.quantity:
                raise HTTPException(400, f"Estoque insuficiente: {p.name}")

            list_price = money(inventory.price)
            cost = money(inventory.average_cost)
            line_gross = money(list_price * line.quantity)

            # Prioridade do contrato novo:
            # 1) discount_total = desconto em R$ sobre a linha inteira
            # 2) discount_percent = percentual sobre a linha inteira
            # 3) discount_unit = compatibilidade com clientes antigos
            if line.discount_total is not None:
                line_discount = money(line.discount_total)
            elif line.discount_percent is not None:
                pct = Decimal(str(line.discount_percent))
                line_discount = money(line_gross * pct / Decimal("100"))
            else:
                legacy_discount_unit = money(line.discount_unit)
                line_discount = money(legacy_discount_unit * line.quantity)

            if line_discount > line_gross:
                raise HTTPException(400, f"Desconto maior que o valor da linha: {p.name}")

            discount_pct = (
                line_discount / line_gross * Decimal("100")
                if line_gross
                else Decimal("0")
            )
            if discount_pct > limit:
                raise HTTPException(
                    403,
                    f"Desconto de {discount_pct.quantize(Decimal('0.01'))}% excede o limite de {limit}% para o perfil {user.role}: {p.name}",
                )

            line_net = money(line_gross - line_discount)
            line_cmv = money(cost * line.quantity)

            # Estes campos unitários são snapshots médios para exibição/compatibilidade.
            # Os totais da linha são a verdade financeira, evitando erro de centavos
            # quando um desconto fixo não é divisível exatamente pela quantidade.
            discount_unit = money(line_discount / line.quantity)
            effective_unit = money(line_net / line.quantity)

            gross += line_gross
            discounts += line_discount
            net += line_net
            cmv += line_cmv
            prepared.append(
                (
                    p,
                    inventory,
                    line,
                    list_price,
                    discount_unit,
                    effective_unit,
                    cost,
                    line_gross,
                    line_discount,
                    line_net,
                    line_cmv,
                )
            )

        sale = Sale(
            company_id=user.company_id,
            store_id=user.store_id,
            total=money(net),
            gross_total=money(gross),
            discount_total=money(discounts),
            cmv_total=money(cmv),
            gross_margin=money(net - cmv),
            payment_method=data.payment_method,
            user_id=user.id,
            cash_session_id=cash_session.id,
        )
        db.add(sale)
        db.flush()

        for (
            p,
            inventory,
            line,
            list_price,
            discount_unit,
            effective_unit,
            cost,
            line_gross,
            line_discount,
            line_net,
            line_cmv,
        ) in prepared:
            inventory.stock -= line.quantity
            db.add(
                SaleItem(
                    sale_id=sale.id,
                    product_id=p.id,
                    quantity=line.quantity,
                    list_unit_price=list_price,
                    discount_unit=discount_unit,
                    effective_unit_price=effective_unit,
                    unit_cost=cost,
                    gross_total=line_gross,
                    discount_total=line_discount,
                    net_total=line_net,
                    cmv_total=line_cmv,
                    unit_price=effective_unit,
                )
            )
            db.add(
                StockMovement(
                    company_id=user.company_id,
                    store_id=user.store_id,
                    product_id=p.id,
                    type="VENDA",
                    quantity=-line.quantity,
                    reference=f"VENDA:{sale.id}",
                    user_id=user.id,
                )
            )

        record_sale(db, cash_session, sale, user.id)
        db.commit()
        db.refresh(sale)
    except Exception:
        db.rollback()
        raise

    margin_pct = money((sale.gross_margin / sale.total) * 100) if sale.total else Decimal("0")
    return {
        "id": sale.id,
        "gross_total": float(sale.gross_total),
        "discount_total": float(sale.discount_total),
        "total": float(sale.total),
        "cmv_total": float(sale.cmv_total),
        "gross_margin": float(sale.gross_margin),
        "gross_margin_percent": float(margin_pct),
        "payment_method": sale.payment_method,
    }
