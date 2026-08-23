from decimal import Decimal


def calculate(list_price, discount, cost, quantity):
    list_price=Decimal(str(list_price));discount=Decimal(str(discount));cost=Decimal(str(cost));quantity=Decimal(str(quantity))
    effective=list_price-discount
    return {
        "gross": list_price*quantity,
        "discount": discount*quantity,
        "net": effective*quantity,
        "cmv": cost*quantity,
        "margin": (effective*quantity)-(cost*quantity),
    }


def test_discount_and_cmv_snapshot_math():
    result=calculate("10.00","1.50","4.20",3)
    assert result["gross"] == Decimal("30.00")
    assert result["discount"] == Decimal("4.50")
    assert result["net"] == Decimal("25.50")
    assert result["cmv"] == Decimal("12.60")
    assert result["margin"] == Decimal("12.90")
