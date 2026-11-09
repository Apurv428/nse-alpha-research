"""Weekly rebalance dates, decile portfolios, P0 spread series, turnover, signal autocorrelation (PRD section 6)."""
from __future__ import annotations

import numpy as np
import polars as pl
from scipy.stats import spearmanr


def weekly_dates(calendar: pl.DataFrame) -> pl.DataFrame:
    """Last session of each ISO week = the signal date of a weekly rebalance (fill at the next close)."""
    c = calendar.with_columns(pl.col("trade_date").dt.iso_year().alias("iy"), pl.col("trade_date").dt.week().alias("iw"))
    return c.group_by("iy", "iw").agg(trade_date=pl.col("trade_date").max(), sess=pl.col("sess").max()).sort("trade_date").select("trade_date", "sess")


def deciles(scores: pl.DataFrame, fwd5: pl.DataFrame, score_col: str, wk: pl.DataFrame, n_bins: int = 10) -> pl.DataFrame:
    """(signal, trade_date, decile, ret) at weekly dates: mean 5-day forward return of each score decile (10 = highest)."""
    s = scores.join(wk.select("trade_date"), on="trade_date").select("trade_date", "sid", "signal", pl.col(score_col).alias("score"))
    j = s.join(fwd5.select("trade_date", "sid", "fwd_ret"), on=["trade_date", "sid"])
    j = j.with_columns(((pl.col("score").rank("ordinal").over("signal", "trade_date") - 1) * n_bins
                        // pl.len().over("signal", "trade_date") + 1).cast(pl.Int32).alias("decile"))
    return j.group_by("signal", "trade_date", "decile").agg(ret=pl.col("fwd_ret").mean(), n=pl.len()).sort("signal", "trade_date", "decile")


def spread_series(dec: pl.DataFrame, n_bins: int = 10) -> pl.DataFrame:
    top = dec.filter(pl.col("decile") == n_bins).select("signal", "trade_date", pl.col("ret").alias("top"))
    bot = dec.filter(pl.col("decile") == 1).select("signal", "trade_date", pl.col("ret").alias("bot"))
    return top.join(bot, on=["signal", "trade_date"]).select("signal", pl.col("trade_date").alias("date"), (pl.col("top") - pl.col("bot")).alias("ret")).sort("signal", "date")


def decile_table(dec: pl.DataFrame, spread: pl.DataFrame, n_bins: int = 10) -> pl.DataFrame:
    rows = []
    for sig in dec["signal"].unique(maintain_order=True):
        m = dec.filter(pl.col("signal") == sig).group_by("decile").agg(r=pl.col("ret").mean()).sort("decile")
        sp = spread.filter(pl.col("signal") == sig)["ret"].drop_nulls().to_numpy()
        mono = float(spearmanr(m["decile"].to_numpy(), m["r"].to_numpy())[0]) if m.height > 2 else float("nan")
        row = {"signal": sig, **{f"D{d}": float(r) for d, r in zip(m["decile"], m["r"])}, "monotonicity": mono,
               "spread_mean_weekly": float(sp.mean()), "spread_sharpe_ann": float(sp.mean() / sp.std(ddof=1) * np.sqrt(52)) if len(sp) > 2 else float("nan"),
               "n_weeks": len(sp)}
        rows.append(row)
    return pl.DataFrame(rows)


def top_decile_turnover(scores: pl.DataFrame, score_col: str, wk: pl.DataFrame, n_bins: int = 10) -> pl.DataFrame:
    """Mean of 1/2 sum_i |w_t - w_{t-1}| per weekly rebalance for the equal-weight top decile."""
    s = scores.join(wk.select("trade_date"), on="trade_date").select("trade_date", "sid", "signal", pl.col(score_col).alias("score"))
    s = s.with_columns(((pl.col("score").rank("ordinal").over("signal", "trade_date") - 1) * n_bins // pl.len().over("signal", "trade_date")).alias("d"))
    top = s.filter(pl.col("d") == n_bins - 1).with_columns((1.0 / pl.len().over("signal", "trade_date")).alias("w")).select("signal", "trade_date", "sid", "w")
    dates = top.select("trade_date").unique().sort("trade_date").with_row_index("i")
    cur = top.join(dates, on="trade_date")
    prev = cur.select("signal", "sid", (pl.col("i") + 1).alias("i"), pl.col("w").alias("w_prev"))
    j = cur.join(prev, on=["signal", "sid", "i"], how="full", coalesce=True).with_columns(pl.col("w").fill_null(0.0), pl.col("w_prev").fill_null(0.0))
    t = j.group_by("signal", "i").agg(turnover=0.5 * (pl.col("w") - pl.col("w_prev")).abs().sum()).filter((pl.col("i") > 0) & (pl.col("i") < dates.height))
    return t.group_by("signal").agg(mean_turnover=pl.col("turnover").mean(), n_rebalances=pl.len()).sort("signal")


def signal_autocorr(scores: pl.DataFrame, score_col: str, calendar: pl.DataFrame, lag: int = 5) -> pl.DataFrame:
    """Mean over dates of Spearman(z_t, z_{t-lag}) across names (a proxy for trading cost)."""
    cal = calendar.select("trade_date", "sess")
    s = scores.select("trade_date", "sid", "signal", pl.col(score_col).alias("z")).join(cal, on="trade_date")
    prev = s.select("signal", "sid", (pl.col("sess") + lag).alias("sess"), pl.col("z").alias("z_prev"))
    j = s.join(prev, on=["signal", "sid", "sess"])
    g = j.group_by("signal", "trade_date").agg(rho=pl.corr(pl.col("z").rank(), pl.col("z_prev").rank()), n=pl.len()).filter(pl.col("n") >= 30)
    return g.group_by("signal").agg(autocorr_5=pl.col("rho").mean()).sort("signal")
