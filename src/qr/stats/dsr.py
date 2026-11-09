"""Probabilistic and Deflated Sharpe ratio (Bailey and Lopez de Prado, 2014; PRD section 9.4).

All Sharpe ratios are per-period (weekly). gamma3 = skewness, gamma4 = kurtosis (NOT excess).
N is reported two ways: N_all (every logged trial) and N_eff (hierarchical clustering of the trials' weekly return
series on 1 - rho, trials with rho > 0.7 sharing a cluster). Var[SR] is taken across all trials.
"""
from __future__ import annotations

import math

import numpy as np
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import squareform
from scipy.stats import norm

EULER_GAMMA = 0.5772156649015329


def psr(sr: float, T: int, skew: float, kurt: float, sr_star: float = 0.0) -> float:
    denom = 1.0 - skew * sr + (kurt - 1.0) / 4.0 * sr * sr
    if T < 2 or denom <= 0:
        return float("nan")
    return float(norm.cdf((sr - sr_star) * math.sqrt(T - 1) / math.sqrt(denom)))


def expected_max_sr(var_sr: float, n_trials: float) -> float:
    """SR* = sqrt(Var[SR]) * ((1 - gamma) Phi^-1(1 - 1/N) + gamma Phi^-1(1 - 1/(N e)))."""
    if n_trials <= 1:
        return 0.0
    s = math.sqrt(var_sr)
    return s * ((1 - EULER_GAMMA) * norm.ppf(1 - 1.0 / n_trials) + EULER_GAMMA * norm.ppf(1 - 1.0 / (n_trials * math.e)))


def dsr(sr: float, T: int, skew: float, kurt: float, var_sr: float, n_trials: float) -> dict:
    sr_star = expected_max_sr(var_sr, n_trials)
    return {"dsr": psr(sr, T, skew, kurt, sr_star), "sr_star": sr_star, "n_trials": n_trials, "var_sr": var_sr}


def n_eff(returns: np.ndarray, rho: float = 0.7) -> int:
    """Number of clusters among trials. `returns`: (n_trials, T), NaN-padded series are compared on common dates."""
    R = np.asarray(returns, dtype=float)
    n = R.shape[0]
    if n <= 1:
        return n
    C = np.ones((n, n))
    for i in range(n):
        for j in range(i + 1, n):
            ok = np.isfinite(R[i]) & np.isfinite(R[j])
            c = np.corrcoef(R[i][ok], R[j][ok])[0, 1] if ok.sum() > 2 else 0.0
            C[i, j] = C[j, i] = 0.0 if not np.isfinite(c) else c
    D = np.clip(1.0 - C, 0.0, 2.0)
    np.fill_diagonal(D, 0.0)
    Z = linkage(squareform(D, checks=False), method="average")
    return int(len(set(fcluster(Z, t=1.0 - rho, criterion="distance"))))
