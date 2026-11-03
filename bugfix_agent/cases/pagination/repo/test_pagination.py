import pytest

from pagination import page_count


def test_full_pages():
    assert page_count(20, 10) == 2


def test_empty():
    assert page_count(0, 10) == 0


def test_bad_size():
    with pytest.raises(ValueError):
        page_count(10, 0)
