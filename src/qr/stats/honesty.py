"""Deflated Sharpe with the true ledger trial count, N_eff, and bootstrap CIs for a headline weekly return series
(PRD section 9). Weekly per-period Sharpe throughout; annualised only for display."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import polars as pl

from qr.guard import trial_ledger as L
from qr.stats import bootstrap as B
from qr.stats import dsr as D

ROOT = Path(__file__).resolve().parents[3]


def _matrix(trials: list[dict]):
    series = []
    for t in trials:
        p = Path(t["returns_path"])
        p = p if p.is_absolute() else ROOT / p
        if p.exists():
            series.append(pl.read_parquet(p).select("date", "ret"))
    if not series:
        return np.empty((0, 0)), []
    dates = sorted(set().union(*[set(s["date"].to_list()) for s in series]))
    ix = {d: i for i, d in enumerate(dates)}
    R = np.full((len(series), len(dates)), np.nan)
    for k, s in enumerate(series):
        for d, r in zip(s["date"].to_list(), s["ret"].to_list()):
            R[k, ix[d]] = r
    return R, dates


def honesty(weekly: pl.DataFrame, ledger: Path | None = None, B_: int = 10_000, active: bool = False) -> dict:
    """`weekly`: (date, ret) of the headline book. Returns DSR (N_all and N_eff), PSR(0) and bootstrap CIs."""
    trials = L.load_trials(ledger)
    n_all = len(trials)
    r = weekly["ret"].to_numpy()
    mom = L.sharpe_moments(r)
    srs = np.array([t["sr"] for t in trials if t.get("sr") is not None and np.isfinite(t["sr"])])
    var_sr = float(np.var(srs, ddof=1)) if srs.size > 1 else float("nan")
    R, _ = _matrix(trials)
    n_eff = int(D.n_eff(R)) if R.shape[0] > 1 else n_all
    out = {"n_all": n_all, "n_eff": n_eff, "n_obs": mom["n_obs"], "sr_weekly": mom["sr"], "sr_annual": mom["sr"] * np.sqrt(52),
           "skew": mom["skew"], "kurt": mom["kurt"], "var_sr_across_trials": var_sr,
           "psr0": D.psr(mom["sr"], mom["n_obs"], mom["skew"], mom["kurt"], 0.0)}
    if np.isfinite(var_sr):
        out["dsr_n_all"] = D.dsr(mom["sr"], mom["n_obs"], mom["skew"], mom["kurt"], var_sr, n_all)
        out["dsr_n_eff"] = D.dsr(mom["sr"], mom["n_obs"], mom["skew"], mom["kurt"], var_sr, max(n_eff, 2))
    stat = B.stat_ir if active else B.stat_sharpe
    out["bootstrap_" + ("ir" if active else "sharpe") + "_annual"] = B.bootstrap_ci(r, (lambda a: stat(a, 52.0)), mean_block=4.0, B=B_)
    out["bootstrap_mean_weekly"] = B.bootstrap_ci(r, B.stat_mean, mean_block=4.0, B=B_)
    return out


def write(weekly: pl.DataFrame, path: Path, **kw) -> dict:
    res = honesty(weekly, **kw)
    Path(path).write_text(json.dumps(res, indent=1, default=str))
    return res


def oos_stats(weekly: pl.DataFrame, active: bool = False, B_: int = 10_000) -> dict:
    """OOS window: one pre-declared strategy tested once, so PSR(0) and bootstrap CIs only (no deflation)."""
    r = weekly["ret"].to_numpy()
    m = L.sharpe_moments(r)
    stat = B.stat_ir if active else B.stat_sharpe
    return {"n_obs": m["n_obs"], "sr_weekly": m["sr"], "sr_annual": m["sr"] * np.sqrt(52), "skew": m["skew"], "kurt": m["kurt"],
            "psr0": D.psr(m["sr"], m["n_obs"], m["skew"], m["kurt"], 0.0),
            "bootstrap_" + ("ir" if active else "sharpe") + "_annual": B.bootstrap_ci(r, (lambda a: stat(a, 52.0)), mean_block=4.0, B=B_)}
