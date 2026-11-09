"""Newey-West t-statistic for the mean of a (possibly overlapping-label) series (PRD section 6)."""
from __future__ import annotations

import math

import numpy as np


def nw_lag(T: int, h: int = 1) -> int:
    """L = max(h - 1, floor(4 (T/100)^(2/9)))."""
    return max(h - 1, int(math.floor(4.0 * (T / 100.0) ** (2.0 / 9.0))))


def nw_omega(x: np.ndarray, L: int) -> float:
    """Bartlett-kernel long-run variance: gamma_0 + 2 sum_{l=1..L} (1 - l/(L+1)) gamma_l (1/T normalisation)."""
    x = np.asarray(x, dtype=float)
    T = len(x)
    e = x - x.mean()
    om = float(e @ e) / T
    for l in range(1, min(L, T - 1) + 1):
        om += 2.0 * (1.0 - l / (L + 1.0)) * float(e[l:] @ e[:-l]) / T
    return om


def nw_tstat(x: np.ndarray, h: int = 1, L: int | None = None) -> dict:
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    T = len(x)
    if T < 3:
        return {"mean": float("nan"), "t_nw": float("nan"), "se": float("nan"), "lags": 0, "n": T}
    L = nw_lag(T, h) if L is None else L
    se = math.sqrt(nw_omega(x, L) / T)
    return {"mean": float(x.mean()), "t_nw": float(x.mean() / se) if se > 0 else float("nan"), "se": se, "lags": L, "n": T}


def plain_t(x: np.ndarray) -> float:
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    return float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x))))
