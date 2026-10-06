"""Wilson score interval for binomial proportions — honest small-sample CIs."""

from __future__ import annotations

import math
from typing import Any


def wilson_interval(successes: int, n: int, z: float = 1.96) -> dict[str, Any]:
    """
    Approximate 95% Wilson score interval.
    For n < 30 we still compute it but flag small_sample.
    """
    if n <= 0:
        return {
            "n": 0,
            "rate": None,
            "low": None,
            "high": None,
            "small_sample": True,
            "note": "no trials",
        }
    phat = successes / n
    z2 = z * z
    denom = 1 + z2 / n
    center = (phat + z2 / (2 * n)) / denom
    margin = (z * math.sqrt((phat * (1 - phat) + z2 / (4 * n)) / n)) / denom
    return {
        "n": n,
        "successes": successes,
        "rate": round(phat, 4),
        "ci95_low": round(max(0.0, center - margin), 4),
        "ci95_high": round(min(1.0, center + margin), 4),
        "small_sample": n < 30,
        "note": "Small-n Wilson interval; not a substitute for a large held-out study."
        if n < 30
        else "Wilson 95% CI",
    }
