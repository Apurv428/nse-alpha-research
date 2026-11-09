"""Cumulative and marginal decay, correlation matrices, stability splits (PRD section 6)."""
from __future__ import annotations

import numpy as np
import polars as pl

from qr.eval.ic import MIN_NAMES
from qr.stats.newey_west import nw_tstat

K_MAX = 20


def marginal_returns(dense: pl.LazyFrame, k_max: int = K_MAX) -> pl.DataFrame:
    """Wide frame (trade_date, sid, r0..r20): the 1-day return of session t+2+k, i.e. the return earned k days after the
    fill at close t+1 (DECISIONS D-018). Requires a traded row on that session."""
    d = dense.sort("sid", "sess")
    cols = [pl.when(pl.col("traded_row").shift(-(2 + k)).over("sid")).then(pl.col("ret_1d").shift(-(2 + k)).over("sid")).otherwise(None).alias(f"r{k}")
            for k in range(k_max + 1)]
    return d.select("trade_date", "sid", *cols).collect()


def marginal_decay(scores: pl.DataFrame, score_col: str, mr: pl.DataFrame, k_max: int = K_MAX) -> pl.DataFrame:
    rows = []
    for sig in scores["signal"].unique(maintain_order=True):
        s = scores.filter(pl.col("signal") == sig).select("trade_date", "sid", pl.col(score_col).alias("score")).join(mr, on=["trade_date", "sid"])
        vals = []
        for k in range(k_max + 1):
            g = s.filter(pl.col(f"r{k}").is_not_null()).group_by("trade_date").agg(
                ic=pl.corr(pl.col("score").rank(), pl.col(f"r{k}").rank()), n=pl.len()).filter(pl.col("n") >= MIN_NAMES)
            vals.append(float(g["ic"].mean()))
        half = next((k for k, v in enumerate(vals) if vals[0] > 0 and v < 0.5 * vals[0]), None)
        rows.append({"signal": sig, **{f"k{k}": v for k, v in enumerate(vals)}, "half_life_k": half})
    return pl.DataFrame(rows)


def corr_scores(scores: pl.DataFrame, score_col: str) -> pl.DataFrame:
    """Time mean of the daily cross-sectional Spearman between each pair of signals."""
    w = scores.select("trade_date", "sid", "signal", pl.col(score_col).alias("v")).pivot(on="signal", index=["trade_date", "sid"], values="v")
    names = [c for c in w.columns if c not in ("trade_date", "sid")]
    ranked = w.with_columns([pl.col(c).rank().over("trade_date").alias(c) for c in names])
    mats = []
    for _, g in ranked.group_by("trade_date"):
        x = g.select(names).drop_nulls()
        if x.height >= MIN_NAMES:
            mats.append(np.corrcoef(x.to_numpy(), rowvar=False))
    M = np.nanmean(np.stack(mats), axis=0)
    return pl.DataFrame({"signal": names, **{n: M[:, i] for i, n in enumerate(names)}})


def corr_ic(ics: pl.DataFrame, h: int = 5) -> pl.DataFrame:
    w = ics.filter(pl.col("h") == h).pivot(on="signal", index="trade_date", values="rank_ic").drop("trade_date")
    names = w.columns
    M = np.corrcoef(w.drop_nulls().to_numpy(), rowvar=False)
    return pl.DataFrame({"signal": names, **{n: M[:, i] for i, n in enumerate(names)}})


def stability(scores: pl.DataFrame, score_col: str, fwd5: pl.DataFrame, ctx: pl.DataFrame, bench: pl.DataFrame, calendar: pl.DataFrame) -> pl.DataFrame:
    """Rank IC (h=5) by calendar year, size half (rank_liq <= 375 vs > 375) and market state (trailing-12m Nifty 500 > 0)."""
    cal = calendar.select("trade_date", "sess")
    b = bench.select("trade_date", "n500_close").join(cal, on="trade_date").sort("sess")
    b = b.with_columns((pl.col("n500_close") / pl.col("n500_close").shift(252) - 1).alias("tr12")).select(
        "trade_date", pl.when(pl.col("tr12") > 0).then(pl.lit("up")).when(pl.col("tr12") <= 0).then(pl.lit("down")).otherwise(None).alias("state"))
    s = scores.select("trade_date", "sid", "signal", pl.col(score_col).alias("score")).join(fwd5.select("trade_date", "sid", "fwd_ret"), on=["trade_date", "sid"]) \
        .join(ctx.select("trade_date", "sid", "rank_liq"), on=["trade_date", "sid"]).join(b, on="trade_date", how="left") \
        .with_columns(pl.col("trade_date").dt.year().cast(pl.String).alias("year"),
                      pl.when(pl.col("rank_liq") <= 375).then(pl.lit("top375")).otherwise(pl.lit("376-750")).alias("size_half"))
    rows = []
    for split in ("year", "size_half", "state"):
        g = s.filter(pl.col(split).is_not_null()).group_by("signal", split, "trade_date").agg(
            r=pl.corr(pl.col("score").rank(), pl.col("fwd_ret").rank()), n=pl.len()).filter(pl.col("n") >= 15)
        for (sig, grp), gg in g.group_by(["signal", split]):
            x = gg.sort("trade_date")["r"].drop_nulls().to_numpy()
            nw = nw_tstat(x, 5)
            rows.append({"signal": sig, "split": split, "group": str(grp), "mean_rank_ic": nw["mean"], "t_nw": nw["t_nw"], "n_dates": len(x)})
    return pl.DataFrame(rows).sort("signal", "split", "group")
