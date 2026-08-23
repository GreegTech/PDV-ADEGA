from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth import current_user
from .database import get_db
from .main import discount_limit_for_role, money
from .models import Product, Sale, SaleItem, StockMovement, User
from .schemas import SaleCreate

router = APIRouter()


@router.post("/sales")
def create_sale_line_discount(
    data: SaleCreate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
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
        for line in data.items:
            p = db.execute(
                select(Product).where(Product.id == line.product_id).with_for_update()
            ).scalar_one_or_none()
            if not p:
                raise HTTPException(404, f"Produto {line.product_id} não encontrado")
            if not p.active:
                raise HTTPException(400, f"Produto desativado e indisponível para venda: {p.name}")
            if p.stock < line.quantity:
                raise HTTPException(400, f"Estoque insuficiente: {p.name}")

            list_price = money(p.price)
            cost = money(p.cost)
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
            total=money(net),
            gross_total=money(gross),
            discount_total=money(discounts),
            cmv_total=money(cmv),
            gross_margin=money(net - cmv),
            payment_method=data.payment_method,
            user_id=user.id,
        )
        db.add(sale)
        db.flush()

        for (
            p,
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
            p.stock -= line.quantity
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
                    product_id=p.id,
                    type="VENDA",
                    quantity=-line.quantity,
                    reference=f"VENDA:{sale.id}",
                    user_id=user.id,
                )
            )

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
