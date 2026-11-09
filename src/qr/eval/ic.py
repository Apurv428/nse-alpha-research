"""Daily cross-sectional IC / rank IC, Newey-West inference, ICIR, hit rate, Holm (PRD section 6)."""
from __future__ import annotations

import numpy as np
import polars as pl
from scipy.stats import norm

from qr.stats.newey_west import nw_lag, nw_tstat, plain_t

MIN_NAMES = 30


def ic_series(scores: pl.DataFrame, fwd: pl.DataFrame, score_col: str, by_extra: list[str] | None = None) -> pl.DataFrame:
    """scores: (trade_date, sid, signal, <score_col>); fwd: (trade_date, sid, h, fwd_ret).
    Returns (signal, h, trade_date, ic, rank_ic, n). One pass per signal to bound memory."""
    out = []
    extra = by_extra or []
    for sig in scores["signal"].unique(maintain_order=True):
        s = scores.filter(pl.col("signal") == sig).select("trade_date", "sid", pl.col(score_col).alias("score"), *extra)
        j = s.join(fwd.select("trade_date", "sid", "h", "fwd_ret"), on=["trade_date", "sid"])
        g = j.group_by("h", "trade_date", *extra).agg(
            ic=pl.corr("score", "fwd_ret"),
            rank_ic=pl.corr(pl.col("score").rank(), pl.col("fwd_ret").rank()),
            n=pl.len()).filter(pl.col("n") >= MIN_NAMES)
        out.append(g.with_columns(pl.lit(sig).alias("signal")))
    return pl.concat(out).select("signal", "h", "trade_date", *extra, "ic", "rank_ic", "n").sort("signal", "h", "trade_date")


def summarize(ics: pl.DataFrame, version: str) -> pl.DataFrame:
    rows = []
    for (sig, h), g in ics.group_by(["signal", "h"], maintain_order=True):
        g = g.sort("trade_date")
        ic, ric = g["ic"].drop_nulls().to_numpy(), g["rank_ic"].drop_nulls().to_numpy()
        nw_ic, nw_r = nw_tstat(ic, h), nw_tstat(ric, h)
        no = ric[::h]  # non-overlapping dates
        icir = float(no.mean() / no.std(ddof=1) * np.sqrt(252.0 / h)) if len(no) > 2 and no.std(ddof=1) > 0 else float("nan")
        rows.append({"signal": sig, "version": version, "h": int(h), "n_dates": len(ric), "mean_ic": nw_ic["mean"],
                     "t_nw_ic": nw_ic["t_nw"], "mean_rank_ic": nw_r["mean"], "t_nw": nw_r["t_nw"], "nw_lags": nw_r["lags"],
                     "t_plain_nonoverlap": plain_t(no) if len(no) > 2 else float("nan"), "icir_ann": icir,
                     "hit_rate": float((ric > 0).mean())})
    return pl.DataFrame(rows).sort("version", "signal", "h")


def holm_adjust(p: np.ndarray) -> np.ndarray:
    """Holm step-down adjusted p-values (family-wise error)."""
    p = np.asarray(p, dtype=float)
    order = np.argsort(p)
    m = len(p)
    adj = np.empty(m)
    run = 0.0
    for rank, i in enumerate(order):
        run = max(run, (m - rank) * p[i])
        adj[i] = min(1.0, run)
    return adj


def holm_table(summary: pl.DataFrame, h: int = 5, t_hurdle: float = 3.0, alpha: float = 0.05) -> pl.DataFrame:
    """Holm across the 16 tests (8 signals x raw/neutral) at horizon h. Pre-registered sign is +."""
    s = summary.filter(pl.col("h") == h).sort("version", "signal")
    t = s["t_nw"].to_numpy()
    p = 2.0 * (1.0 - norm.cdf(np.abs(t)))
    adj = holm_adjust(p)
    return s.select("signal", "version", "mean_rank_ic", "t_nw").with_columns(
        pl.Series("p_two_sided", p), pl.Series("p_holm", adj),
        pl.Series("pass_holm_t3", (adj < alpha) & (t >= t_hurdle)),
        pl.Series("sig_wrong_sign", (adj < alpha) & (t <= -t_hurdle)))
