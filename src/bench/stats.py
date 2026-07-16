"""Statistics: pass-rate confidence intervals and the three-bucket comparison.

Design stance: with 20-50 tasks and a handful of trials each, the data
supports coarse decisions only. We never emit fine-grained rankings; each
challenger is bucketed against the incumbent as clearly_better /
roughly_equal / clearly_worse, using a Wilson score interval per rate and a
Newcombe score interval for the difference.
"""

from __future__ import annotations

import dataclasses
import math

Z95 = 1.959963984540054

CLEARLY_BETTER = "clearly_better"
ROUGHLY_EQUAL = "roughly_equal"
CLEARLY_WORSE = "clearly_worse"
INSUFFICIENT_DATA = "insufficient_data"


def wilson_interval(successes: int, n: int, z: float = Z95) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion."""
    if n <= 0:
        return (0.0, 1.0)
    if not 0 <= successes <= n:
        raise ValueError(f"successes={successes} out of range for n={n}")
    p = successes / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    margin = (z / denom) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    lo = 0.0 if successes == 0 else max(0.0, center - margin)
    hi = 1.0 if successes == n else min(1.0, center + margin)
    return (lo, hi)


def newcombe_diff_interval(
    s1: int, n1: int, s2: int, n2: int, z: float = Z95
) -> tuple[float, float]:
    """Newcombe (method 10) score interval for p1 - p2."""
    if n1 <= 0 or n2 <= 0:
        return (-1.0, 1.0)
    p1, p2 = s1 / n1, s2 / n2
    l1, u1 = wilson_interval(s1, n1, z)
    l2, u2 = wilson_interval(s2, n2, z)
    d = p1 - p2
    lo = d - math.sqrt((p1 - l1) ** 2 + (u2 - p2) ** 2)
    hi = d + math.sqrt((u1 - p1) ** 2 + (p2 - l2) ** 2)
    return (max(-1.0, lo), min(1.0, hi))


@dataclasses.dataclass
class Rate:
    successes: int
    n: int

    @property
    def point(self) -> float:
        return self.successes / self.n if self.n else 0.0

    @property
    def interval(self) -> tuple[float, float]:
        return wilson_interval(self.successes, self.n)


@dataclasses.dataclass
class Comparison:
    challenger: Rate
    incumbent: Rate
    bucket: str
    diff: float
    diff_interval: tuple[float, float]


def compare(
    challenger: Rate,
    incumbent: Rate,
    min_trials: int = 6,
    equivalence_margin: float = 0.10,
) -> Comparison:
    """Bucket a challenger against the incumbent.

    - insufficient_data: either side has fewer than ``min_trials`` trials.
    - clearly_better:    the diff CI excludes zero on the positive side.
    - clearly_worse:     the diff CI excludes zero on the negative side, AND
                         the point estimate is worse by more than the
                         equivalence margin (a statistically-real but tiny
                         deficit still counts as roughly equal).
    - roughly_equal:     everything else.
    """
    lo, hi = newcombe_diff_interval(
        challenger.successes, challenger.n, incumbent.successes, incumbent.n
    )
    diff = challenger.point - incumbent.point
    if challenger.n < min_trials or incumbent.n < min_trials:
        bucket = INSUFFICIENT_DATA
    elif lo > 0:
        bucket = CLEARLY_BETTER
    elif hi < 0 and diff < -equivalence_margin:
        bucket = CLEARLY_WORSE
    else:
        bucket = ROUGHLY_EQUAL
    return Comparison(
        challenger=challenger,
        incumbent=incumbent,
        bucket=bucket,
        diff=diff,
        diff_interval=(lo, hi),
    )
