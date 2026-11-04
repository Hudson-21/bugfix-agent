import pytest

from inventory import reserve


def test_empty_order_keeps_stock():
    stock = {"tea": 5, "coffee": 0}
    assert reserve(stock, []) is None
    assert stock == {"tea": 5, "coffee": 0}


def test_success_deducts_stock_without_changing_order():
    stock = {"tea": 5, "coffee": 3, "milk": 0}
    lines = [("tea", 2), ("coffee", 3)]
    assert reserve(stock, lines) is None
    assert stock == {"tea": 3, "coffee": 0, "milk": 0}
    assert lines == [("tea", 2), ("coffee", 3)]


def test_repeated_product_with_enough_stock():
    stock = {"tea": 5}
    assert reserve(stock, [("tea", 2), ("tea", 3)]) is None
    assert stock == {"tea": 0}


def test_first_item_shortage_keeps_stock():
    stock = {"tea": 1}
    with pytest.raises(ValueError):
        reserve(stock, [("tea", 2)])
    assert stock == {"tea": 1}


def test_unknown_first_product_is_rejected():
    stock = {"tea": 5}
    with pytest.raises(ValueError):
        reserve(stock, [("coffee", 1)])
    assert stock == {"tea": 5}


@pytest.mark.parametrize("quantity", [0, -1, 1.5, True])
def test_invalid_first_quantity_is_rejected(quantity):
    stock = {"tea": 5}
    with pytest.raises(ValueError):
        reserve(stock, [("tea", quantity)])
    assert stock == {"tea": 5}
