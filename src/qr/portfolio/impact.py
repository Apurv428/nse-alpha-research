"""Spread and market-impact inputs (PRD section 8): Abdi-Ranaldo close-high-low spread, 63-session sigma and ADV.

PIT: the AR term for day tau uses the mid-range of tau+1, so at date t only terms up to tau = t-1 are usable
(`.shift(1)` below). cost_mkt = clip(S/2, floor, 50bp) + Y * sigma * sqrt(Q / ADV)  (per side, fraction of traded value).
"""
from __future__ import annotations

import numpy as np
import polars as pl

HALF_SPREAD_FLOOR = 2e-4
HALF_SPREAD_CAP = 50e-4


def cost_inputs(prices: pl.DataFrame, calendar: pl.DataFrame) -> pl.DataFrame:
    """(sid, sess, half_spread, sigma, adv): spread averaged over 21 terms, sigma = 63-session std of log returns
    (>= 50 obs), ADV = 63-session median traded value in INR (>= 40 obs). All use data up to and including t
    except the AR term, which uses terms up to t-1."""
    rng = prices.group_by("sid").agg(a=pl.col("sess").min(), b=pl.col("sess").max())
    d = rng.with_columns(pl.int_ranges(pl.col("a"), pl.col("b") + 1).alias("sess")).select("sid", "sess").explode("sess")
    px = prices.select("sid", "sess", "high", "low", "close", "price_factor", "ret_1d", "value_inr")
    d = d.join(px, on=["sid", "sess"], how="left").sort("sid", "sess")
    ok = (pl.col("high") > 0) & (pl.col("low") > 0) & (pl.col("close") > 0)
    c = pl.when(ok).then(pl.col("close").log()).otherwise(None)
    eta = pl.when(ok).then((pl.col("high").log() + pl.col("low").log()) / 2.0).otherwise(None)
    d = d.with_columns(c.alias("_c"), eta.alias("_eta"))
    nxt_eta = pl.col("_eta").shift(-1).over("sid")
    nxt_pf = pl.col("price_factor").shift(-1).over("sid")
    term = pl.when(nxt_pf == 1.0).then(4.0 * (pl.col("_c") - pl.col("_eta")) * (pl.col("_c") - nxt_eta)).otherwise(None)
    d = d.with_columns(term.alias("_term"))
    m = pl.col("_term").rolling_mean(21, min_samples=10).over("sid").shift(1).over("sid")  # terms up to t-1 only
    d = d.with_columns(pl.when(pl.col("ret_1d") > -1).then((1 + pl.col("ret_1d")).log()).otherwise(None).alias("_l"))
    out = d.select("sid", "sess",
                   (m.clip(lower_bound=0.0).sqrt() / 2.0).clip(HALF_SPREAD_FLOOR, HALF_SPREAD_CAP).alias("half_spread"),
                   pl.col("_l").rolling_std(63, min_samples=50).over("sid").alias("sigma"),
                   pl.col("value_inr").rolling_median(63, min_samples=40).over("sid").alias("adv"))
    return out


def impact_fraction(sigma: np.ndarray, q_inr: np.ndarray, adv: np.ndarray, Y: float = 1.0) -> np.ndarray:
    """Square-root law: Y * sigma * sqrt(Q / ADV), as a fraction of traded value."""
    with np.errstate(divide="ignore", invalid="ignore"):
        x = Y * sigma * np.sqrt(np.where(adv > 0, q_inr / adv, 0.0))
    return np.nan_to_num(x, nan=0.0, posinf=0.0)
