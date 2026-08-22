from decimal import Decimal, ROUND_HALF_UP

CENT = Decimal("0.01")

def cmp(stock, avg, incoming_qty, incoming_cost):
    result = ((Decimal(stock) * Decimal(str(avg))) + (Decimal(incoming_qty) * Decimal(str(incoming_cost)))) / Decimal(stock + incoming_qty)
    return result.quantize(CENT, rounding=ROUND_HALF_UP)

def test_cmp_equal_batches():
    assert cmp(10, "4.00", 10, "5.00") == Decimal("4.50")

def test_cmp_cheaper_purchase():
    assert cmp(20, "4.50", 5, "3.80") == Decimal("4.36")

def test_first_purchase():
    assert cmp(0, "0", 12, "6.75") == Decimal("6.75")
