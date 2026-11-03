import pytest

from statistics_utils import mean


def test_whole_mean():
    assert mean([2, 4]) == 3


def test_single():
    assert mean([7]) == 7


def test_empty_rejected():
    with pytest.raises(ValueError):
        mean([])
