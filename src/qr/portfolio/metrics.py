"""Performance statistics from a daily NAV series (252-day annualisation). All numbers are computed, never typed."""
from __future__ import annotations

import numpy as np
import polars as pl

ANN = 252.0


def _maxdd(r: np.ndarray) -> float:
    w = np.cumprod(1 + r)
    return float((w / np.maximum.accumulate(w) - 1).min()) if r.size else float("nan")


def weekly(daily: pl.DataFrame, col: str = "ret") -> pl.DataFrame:
    d = daily.drop_nulls(col).with_columns(pl.col("date").dt.iso_year().alias("iy"), pl.col("date").dt.week().alias("iw"))
    return (d.group_by("iy", "iw").agg(date=pl.col("date").max(), ret=(1 + pl.col(col)).product() - 1).sort("date").select("date", "ret"))


def summarize(daily: pl.DataFrame, bench_ret: np.ndarray | None = None, rf_annual: float = 0.065) -> dict:
    d = daily.drop_nulls("ret")
    r = d["ret"].to_numpy()
    rf = rf_annual / ANN
    yrs = (d["date"].max() - d["date"].min()).days / 365.25
    out = {"cagr": float(np.prod(1 + r) ** (1 / yrs) - 1), "vol": float(r.std(ddof=1) * np.sqrt(ANN)),
           "sharpe": float((r - rf).mean() / r.std(ddof=1) * np.sqrt(ANN)), "max_drawdown": _maxdd(r), "years": yrs,
           "avg_holdings_long": float(d["n_long"].mean()), "avg_holdings_short": float(d["n_short"].mean())}
    m = d.with_columns(pl.col("date").dt.year().alias("y"), pl.col("date").dt.month().alias("m")).group_by("y", "m").agg(x=(1 + pl.col("ret")).product() - 1)
    out["worst_month"] = float(m["x"].min())
    w = weekly(d)
    out["weekly_hit_rate"] = float((w["ret"] > 0).mean())
    if bench_ret is not None:
        b = np.asarray(bench_ret, float)
        ok = np.isfinite(b) & np.isfinite(r)
        a = r[ok] - b[ok]
        out.update(active_return=float(a.mean() * ANN), tracking_error=float(a.std(ddof=1) * np.sqrt(ANN)),
                   ir=float(a.mean() / a.std(ddof=1) * np.sqrt(ANN)), beta=float(np.cov(r[ok], b[ok])[0, 1] / b[ok].var(ddof=1)),
                   max_active_drawdown=_maxdd(a), bench_cagr=float(np.prod(1 + b[ok]) ** (1 / yrs) - 1))
    return out
