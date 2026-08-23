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


def calculate_line_discount(list_price, discount_total, cost, quantity):
    list_price=Decimal(str(list_price));discount_total=Decimal(str(discount_total));cost=Decimal(str(cost));quantity=Decimal(str(quantity))
    gross=list_price*quantity
    net=gross-discount_total
    return {
        "gross": gross,
        "discount": discount_total,
        "net": net,
        "effective_unit": net/quantity,
        "cmv": cost*quantity,
        "margin": net-(cost*quantity),
    }


def discount_percent(list_price, discount):
    list_price=Decimal(str(list_price));discount=Decimal(str(discount))
    return (discount/list_price)*Decimal("100") if list_price else Decimal("0")


def test_discount_and_cmv_snapshot_math():
    result=calculate("10.00","1.50","4.20",3)
    assert result["gross"] == Decimal("30.00")
    assert result["discount"] == Decimal("4.50")
    assert result["net"] == Decimal("25.50")
    assert result["cmv"] == Decimal("12.60")
    assert result["margin"] == Decimal("12.90")


def test_fixed_discount_is_total_for_line_not_per_unit():
    result=calculate_line_discount("10.00","3.00","4.20",3)
    assert result["gross"] == Decimal("30.00")
    assert result["discount"] == Decimal("3.00")
    assert result["net"] == Decimal("27.00")
    assert result["effective_unit"] == Decimal("9.00")


def test_fixed_line_discount_keeps_exact_total_when_not_evenly_divisible():
    result=calculate_line_discount("10.00","1.00","4.20",3)
    assert result["discount"] == Decimal("1.00")
    assert result["net"] == Decimal("29.00")


def test_discount_percentage_policy_math():
    assert discount_percent("10.00","1.00") == Decimal("10.0")
    assert discount_percent("10.00","2.00") == Decimal("20.0")
    assert discount_percent("10.00","10.00") == Decimal("100")
