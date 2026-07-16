import math

import pytest

from bench.stats import (
    CLEARLY_BETTER,
    CLEARLY_WORSE,
    INSUFFICIENT_DATA,
    ROUGHLY_EQUAL,
    Rate,
    compare,
    newcombe_diff_interval,
    wilson_interval,
)


def test_wilson_contains_point_estimate():
    lo, hi = wilson_interval(7, 10)
    assert lo < 0.7 < hi
    assert 0.0 <= lo <= hi <= 1.0


def test_wilson_extremes():
    lo, hi = wilson_interval(0, 10)
    assert lo == 0.0 and hi < 0.35
    lo, hi = wilson_interval(10, 10)
    assert lo > 0.65 and hi == 1.0


def test_wilson_zero_n():
    assert wilson_interval(0, 0) == (0.0, 1.0)


def test_wilson_rejects_bad_input():
    with pytest.raises(ValueError):
        wilson_interval(11, 10)


def test_wilson_known_value():
    # Classic worked example: 15/20 -> approximately (0.531, 0.888)
    lo, hi = wilson_interval(15, 20)
    assert math.isclose(lo, 0.531, abs_tol=0.005)
    assert math.isclose(hi, 0.888, abs_tol=0.005)


def test_newcombe_symmetric_when_equal():
    lo, hi = newcombe_diff_interval(5, 10, 5, 10)
    assert lo < 0 < hi
    assert math.isclose(lo, -hi, abs_tol=1e-9)


def test_compare_insufficient_data():
    c = compare(Rate(2, 3), Rate(3, 3))
    assert c.bucket == INSUFFICIENT_DATA


def test_compare_roughly_equal():
    c = compare(Rate(27, 30), Rate(28, 30))
    assert c.bucket == ROUGHLY_EQUAL


def test_compare_clearly_worse():
    c = compare(Rate(5, 30), Rate(28, 30))
    assert c.bucket == CLEARLY_WORSE


def test_compare_clearly_better():
    c = compare(Rate(28, 30), Rate(5, 30))
    assert c.bucket == CLEARLY_BETTER


def test_small_statistical_deficit_is_roughly_equal():
    # Statistically detectable but within the 10-point equivalence margin.
    c = compare(Rate(920, 1000), Rate(970, 1000))
    assert c.diff_interval[1] < 0  # statistically worse...
    assert c.bucket == ROUGHLY_EQUAL  # ...but not practically worse
