"""Pure-stdlib statistics helpers for benchmark reports."""

from __future__ import annotations

import math
from typing import Sequence, Tuple


def wilson_ci(hits: int, n: int, z: float = 1.96) -> Tuple[float, float]:
    """Return the Wilson score interval for a binomial proportion."""
    if n == 0:
        return (0.0, 0.0)

    p = hits / n
    z2 = z * z
    denom = 1.0 + z2 / n
    centre = (p + z2 / (2.0 * n)) / denom
    margin = z * math.sqrt(p * (1.0 - p) / n + z2 / (4.0 * n * n)) / denom
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def mean_std(xs: Sequence[float]) -> Tuple[float, float]:
    """Return mean and sample standard deviation, with std 0 for n < 2."""
    n = len(xs)
    if n == 0:
        return (0.0, 0.0)

    mean = sum(xs) / n
    if n < 2:
        return (mean, 0.0)

    variance = sum((x - mean) ** 2 for x in xs) / (n - 1)
    return (mean, math.sqrt(variance))


def percentile(xs: Sequence[float], p: float) -> float:
    """Return the linear-interpolated percentile, or 0.0 for empty input."""
    if not xs:
        return 0.0

    ordered = sorted(xs)
    if len(ordered) == 1:
        return ordered[0]

    k = (len(ordered) - 1) * (p / 100.0)
    lo = math.floor(k)
    hi = math.ceil(k)
    if lo == hi:
        return ordered[int(k)]

    return ordered[lo] * (hi - k) + ordered[hi] * (k - lo)


def median(xs: Sequence[float]) -> float:
    """Return the 50th percentile."""
    return percentile(xs, 50.0)
