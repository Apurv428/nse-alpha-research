"""Signal registry (PRD section 5). Every signal is a pure function
`(panel: pl.LazyFrame) -> pl.LazyFrame[trade_date, sid, raw]` over a DENSE per-sid session panel (one row per
session from the sid's first to last trade; non-trading sessions are null observations, not zeros).

`@signal(name, window, min_obs, sign)` fixes the sign and window BEFORE any IC is seen (pre-registration).
Orientation: a higher score means a higher expected return (sign is documented, the function already returns the
oriented score). Signals use only data dated <= t.
"""
from __future__ import annotations

from typing import Callable

import polars as pl

REGISTRY: dict[str, dict] = {}


def signal(name: str, window: int, min_obs: int, sign: int):
    def deco(fn: Callable[[pl.LazyFrame], pl.LazyFrame]):
        REGISTRY[name] = {"fn": fn, "window": window, "min_obs": min_obs, "sign": sign}
        return fn
    return deco


def dense_panel(prices: pl.DataFrame, calendar: pl.DataFrame, bench: pl.DataFrame) -> pl.LazyFrame:
    """One row per (sid, session) from first to last trade. Adds lret = ln(1+ret_1d), traded flag and the
    Nifty 500 log return `m` (missing market days are null)."""
    rng = prices.group_by("sid").agg(a=pl.col("sess").min(), b=pl.col("sess").max())
    d = (rng.with_columns(pl.int_ranges(pl.col("a"), pl.col("b") + 1).alias("sess")).select("sid", "sess").explode("sess")
         .join(calendar, on="sess", how="left"))
    px = prices.select("sid", "sess", "ret_1d", "value_inr", "deliv_pct")
    mk = bench.sort("trade_date").select("trade_date", (pl.col("n500_close") / pl.col("n500_close").shift(1)).log().alias("m"))
    d = (d.join(px, on=["sid", "sess"], how="left").join(mk, on="trade_date", how="left").sort("sid", "sess")
         .with_columns(pl.col("ret_1d").is_not_null().alias("has_ret"),
                       pl.when(pl.col("ret_1d") > -1).then((1 + pl.col("ret_1d")).log()).otherwise(None).alias("lret"),
                       pl.col("value_inr").is_not_null().alias("traded_row")))
    return d.lazy()


def _over(e: pl.Expr) -> pl.Expr:
    return e.over("sid")


@signal("MOM_12_1", window=231, min_obs=200, sign=+1)
def mom_12_1(d: pl.LazyFrame) -> pl.LazyFrame:
    # sum of l_{t-k}, k = 21..251  == 231-session rolling sum evaluated at t-21
    raw = _over(pl.col("lret").rolling_sum(231, min_samples=200).shift(21))
    return d.select("trade_date", "sid", raw.alias("raw"))


@signal("REV_5", window=5, min_obs=4, sign=+1)
def rev_5(d: pl.LazyFrame) -> pl.LazyFrame:
    return d.select("trade_date", "sid", (-_over(pl.col("lret").rolling_sum(5, min_samples=4))).alias("raw"))


@signal("LOWVOL_63", window=63, min_obs=50, sign=+1)
def lowvol_63(d: pl.LazyFrame) -> pl.LazyFrame:
    return d.select("trade_date", "sid", (-_over(pl.col("lret").rolling_std(63, min_samples=50))).alias("raw"))


@signal("IVOL_63", window=63, min_obs=50, sign=+1)
def ivol_63(d: pl.LazyFrame) -> pl.LazyFrame:
    """-sd of residuals from l = a + b m over the last 63 sessions; closed-form rolling OLS on rows where both exist."""
    ok = pl.col("lret").is_not_null() & pl.col("m").is_not_null()
    y, x = pl.when(ok).then(pl.col("lret")).otherwise(None), pl.when(ok).then(pl.col("m")).otherwise(None)
    r = lambda e: _over(e.fill_null(0.0).rolling_sum(63, min_samples=1))
    f = d.with_columns(r(ok.cast(pl.Float64)).alias("_n"), r(x).alias("_sx"), r(y).alias("_sy"),
                       r(x * y).alias("_sxy"), r(x * x).alias("_sxx"), r(y * y).alias("_syy"))
    beta = (pl.col("_n") * pl.col("_sxy") - pl.col("_sx") * pl.col("_sy")) / (pl.col("_n") * pl.col("_sxx") - pl.col("_sx") ** 2)
    f = f.with_columns(beta.alias("_b")).with_columns(((pl.col("_sy") - pl.col("_b") * pl.col("_sx")) / pl.col("_n")).alias("_a"))
    sse = (pl.col("_syy") - 2 * pl.col("_a") * pl.col("_sy") - 2 * pl.col("_b") * pl.col("_sxy") + pl.col("_n") * pl.col("_a") ** 2
           + 2 * pl.col("_a") * pl.col("_b") * pl.col("_sx") + pl.col("_b") ** 2 * pl.col("_sxx"))
    sd = pl.when(pl.col("_n") >= 50).then((sse.clip(lower_bound=0.0) / (pl.col("_n") - 2)).sqrt()).otherwise(None)
    return f.select("trade_date", "sid", (-sd).alias("raw"))


@signal("AMIHUD_63", window=63, min_obs=50, sign=+1)
def amihud_63(d: pl.LazyFrame) -> pl.LazyFrame:
    ill = pl.when(pl.col("value_inr") > 0).then(pl.col("ret_1d").abs() / (pl.col("value_inr") / 1e7)).otherwise(None)
    m = _over(ill.rolling_mean(63, min_samples=50))
    return d.select("trade_date", "sid", pl.when(m > 0).then(m.log()).otherwise(None).alias("raw"))


@signal("ABVOL_5_63", window=63, min_obs=45, sign=+1)
def abvol_5_63(d: pl.LazyFrame) -> pl.LazyFrame:
    v = pl.when(pl.col("value_inr") > 0).then(pl.col("value_inr")).otherwise(None)
    short = _over(v.rolling_mean(5, min_samples=4))
    long_ = _over(v.rolling_mean(58, min_samples=45).shift(5))
    return d.select("trade_date", "sid", pl.when((short > 0) & (long_ > 0)).then((short / long_).log()).otherwise(None).alias("raw"))


@signal("DELIV_ABN", window=231, min_obs=180, sign=+1)
def deliv_abn(d: pl.LazyFrame) -> pl.LazyFrame:
    s = _over(pl.col("deliv_pct").rolling_mean(21, min_samples=15))
    l_ = _over(pl.col("deliv_pct").rolling_mean(231, min_samples=180).shift(21))
    return d.select("trade_date", "sid", (s - l_).alias("raw"))


@signal("HIGH52", window=252, min_obs=200, sign=+1)
def high52(d: pl.LazyFrame) -> pl.LazyFrame:
    # I_t = cumulative total-return index (nulls contribute no return); max over t-251..t
    f = d.with_columns(_over((1.0 + pl.col("ret_1d").fill_null(0.0)).cum_prod()).alias("_I"))
    nvalid = _over(pl.col("has_ret").cast(pl.Float64).rolling_sum(252, min_samples=1))
    mx = _over(pl.col("_I").rolling_max(252, min_samples=1))
    return f.select("trade_date", "sid", pl.when(nvalid >= 200).then(pl.col("_I") / mx).otherwise(None).alias("raw"))


def compute_all(dense: pl.LazyFrame, names: list[str] | None = None) -> pl.DataFrame:
    """Long frame (trade_date, sid, signal, raw) for rows where the sid actually traded on t."""
    traded = dense.select("trade_date", "sid", "traded_row")
    outs = []
    for n in (names or list(REGISTRY)):
        r = REGISTRY[n]["fn"](dense).join(traded, on=["trade_date", "sid"]).filter(pl.col("traded_row") & pl.col("raw").is_not_null()
                                                                                    & pl.col("raw").is_finite())
        outs.append(r.select("trade_date", "sid", pl.lit(n).alias("signal"), "raw"))
    return pl.concat(outs).collect()
