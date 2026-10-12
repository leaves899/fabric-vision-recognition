"""Pure, dependency-free evaluation metrics for textile candidate measurements."""
from __future__ import annotations

import math
from statistics import mean


def axis_error_deg(prediction: float, truth: float) -> float:
    """Undirected axis angular error. 0 and 180 degrees denote the same line."""
    a, b = float(prediction), float(truth)
    if not (math.isfinite(a) and math.isfinite(b)):
        raise ValueError("angles must be finite")
    delta = abs((a - b) % 180.0)
    return min(delta, 180.0 - delta)


def density_error_pct(prediction: float, truth: float) -> float:
    """Absolute percentage error, not absolute error in yarns/cm."""
    p, t = float(prediction), float(truth)
    if not (math.isfinite(p) and math.isfinite(t) and t > 0 and p >= 0):
        raise ValueError("density must be finite; truth > 0 and prediction >= 0")
    return 100.0 * abs(p - t) / t


def summarize(values: list[float]) -> dict:
    """Return average/P95/max. Empty means NOT_EVALUATED, never a zero error."""
    if not values:
        return {"n": 0, "mean": None, "p95": None, "max": None}
    data = sorted(float(x) for x in values)
    if any(not math.isfinite(x) for x in data):
        raise ValueError("non-finite metric")
    pos = 0.95 * (len(data) - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    p95 = data[lo] + (pos - lo) * (data[hi] - data[lo])
    return {"n": len(data), "mean": mean(data), "p95": p95, "max": data[-1]}
