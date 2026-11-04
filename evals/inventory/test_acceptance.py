"""Business expectations, kept outside the model's input repository."""

import pytest


@pytest.mark.parametrize("stock,lines,expected", [
    ({"rice": 4, "salt": 0}, [], {"rice": 4, "salt": 0}),
    ({"rice": 6}, [("rice", 2), ("rice", 4)], {"rice": 0}),
    ({"rice": 9, "oil": 4, "salt": 0},
     [("rice", 2), ("oil", 1), ("rice", 3)], {"rice": 4, "oil": 3, "salt": 0}),
    ({"rice": 4, "oil": 3, "untouched": 7},
     [("rice", 1), ("oil", 3)], {"rice": 3, "oil": 0, "untouched": 7}),
], ids=["empty", "duplicate-exact-stock", "interleaved-duplicates", "unrelated-preserved"])
def test_success_updates_the_callers_dictionary(reserve, stock, lines, expected):
    original_lines = list(lines)
    assert reserve(stock, lines) is None
    assert stock == expected
    assert lines == original_lines


@pytest.mark.parametrize("lines", [
    [("rice", 2), ("oil", 5)],
    [("rice", 2), ("missing", 1)],
    [("rice", 2), ("oil", 1), ("rice", 4)],
    [("rice", 2), ("oil", 0)],
    [("rice", 2), ("oil", -1)],
    [("rice", 2), ("oil", 1.5)],
    [("rice", 2), ("oil", True)],
], ids=["late-shortage", "late-unknown", "duplicate-total-shortage", "late-zero",
        "late-negative", "late-fraction", "late-boolean"])
def test_rejected_order_leaves_every_stock_entry_unchanged(reserve, lines):
    stock = {"rice": 5, "oil": 3, "untouched": 0}
    original_lines = list(lines)
    with pytest.raises(ValueError):
        reserve(stock, lines)
    assert stock == {"rice": 5, "oil": 3, "untouched": 0}
    assert lines == original_lines


def test_valid_order_can_follow_a_rejected_order(reserve):
    stock = {"rice": 7, "oil": 2}
    with pytest.raises(ValueError):
        reserve(stock, [("rice", 3), ("oil", 3)])
    assert stock == {"rice": 7, "oil": 2}
    assert reserve(stock, [("rice", 7), ("oil", 2)]) is None
    assert stock == {"rice": 0, "oil": 0}
