"""Stationary block bootstrap (Politis and Romano, 1994). Mean block length 4 weeks (21 for daily), B = 10,000,
fixed and logged seed, 95% percentile intervals (PRD section 9.5)."""
from __future__ import annotations

from typing import Callable

import numpy as np

SEED = 20261109


def sb_indices(T: int, mean_block: float, B: int = 10_000, seed: int = SEED) -> np.ndarray:
    """(B, T) resample indices: each step continues the block with prob 1 - 1/mean_block, else jumps to a random start."""
    rng = np.random.default_rng(seed)
    p = 1.0 / mean_block
    idx = np.empty((B, T), dtype=np.int64)
    idx[:, 0] = rng.integers(0, T, B)
    jump = rng.random((B, T)) < p
    starts = rng.integers(0, T, (B, T))
    for t in range(1, T):
        idx[:, t] = np.where(jump[:, t], starts[:, t], (idx[:, t - 1] + 1) % T)
    return idx


def bootstrap_ci(data: np.ndarray, stat: Callable[[np.ndarray], np.ndarray], mean_block: float = 4.0, B: int = 10_000,
                 seed: int = SEED, alpha: float = 0.05) -> dict:
    """`data`: (T,) or (T, k). `stat` maps a (B, T[, k]) array to (B,). Rows of `data` are resampled together,
    so paired series (e.g. ridge and EW) keep their dependence."""
    data = np.asarray(data, dtype=float)
    idx = sb_indices(len(data), mean_block, B, seed)
    draws = stat(data[idx])
    pt = float(stat(data[None, ...])[0])
    lo, hi = np.nanpercentile(draws, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return {"point": pt, "ci_lo": float(lo), "ci_hi": float(hi), "B": B, "seed": seed, "mean_block": mean_block}


def stat_mean(a):  # (B, T)
    return a.mean(axis=1)


def stat_sharpe(a, periods_per_year: float = 1.0):  # (B, T)
    return a.mean(axis=1) / a.std(axis=1, ddof=1) * np.sqrt(periods_per_year)


def stat_ir(a, periods_per_year: float = 52.0):  # active returns (B, T): mean / sd, annualised
    return a.mean(axis=1) / a.std(axis=1, ddof=1) * np.sqrt(periods_per_year)


def stat_mean_diff(a):  # (B, T, 2): column 0 minus column 1
    return (a[..., 0] - a[..., 1]).mean(axis=1)
