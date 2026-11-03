import pytest

from pricing import payable


def test_regular_discount():
    assert payable(10000, 2000) == 8000


def test_no_discount():
    assert payable(10000, 0) == 10000


def test_exact_discount():
    assert payable(10000, 10000) == 0


def test_negative_amount_rejected():
    with pytest.raises(ValueError):
        payable(-1, 0)


def test_negative_discount_rejected():
    with pytest.raises(ValueError):
        payable(100, -1)
