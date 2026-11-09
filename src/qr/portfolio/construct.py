"""Target-portfolio rules (PRD section 8). Pure functions of one date's scores: no state beyond `held`."""
from __future__ import annotations

import numpy as np


def rank_pct(score: np.ndarray, eligible: np.ndarray) -> np.ndarray:
    """Descending rank / n among eligible names with a finite score (best = small). Ineligible -> nan."""
    ok = eligible & np.isfinite(score)
    out = np.full(score.shape, np.nan)
    idx = np.flatnonzero(ok)
    if idx.size == 0:
        return out
    order = idx[np.argsort(-score[idx], kind="stable")]  # stable: ties broken by position (sid order), deterministic
    out[order] = (np.arange(1, idx.size + 1)) / idx.size
    return out


def select_p1(score: np.ndarray, eligible: np.ndarray, held: np.ndarray, enter: float = 0.10, keep: float = 0.20) -> np.ndarray:
    """Enter in the top `enter`, stay while still in the top `keep` (turnover buffer). Names that are not eligible
    (left the universe, no score) are never kept."""
    p = rank_pct(score, eligible)
    with np.errstate(invalid="ignore"):
        return (p <= enter) | (held & (p <= keep))


def select_p2(score: np.ndarray, eligible: np.ndarray, q: float = 0.20) -> tuple[np.ndarray, np.ndarray]:
    """Long top quintile, short bottom quintile (no buffer, PRD)."""
    p = rank_pct(score, eligible)
    n = int(np.isfinite(p).sum())
    k = int(np.ceil(q * n)) if n else 0
    with np.errstate(invalid="ignore"):
        return p <= q, (p * n > n - k) if n else np.zeros_like(eligible)
