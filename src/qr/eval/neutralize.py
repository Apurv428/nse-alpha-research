"""Cross-sectional processing and neutralization (PRD sections 5 and 6).

Per date, inside the PIT universe: winsorize at the 1st/99th percentiles, standardize, then one OLS of z on
sector dummies (sectors with < 5 names that day merge into Unclassified), the shrunk Dimson beta and size; the
re-standardized residual is z_neu. Beta = sum of the lag-0 and lag-1 univariate betas on a 252-session window
(a simple Dimson-type estimate, DECISIONS D-017), shrunk 0.6 * beta + 0.4.
"""
from __future__ import annotations

import numpy as np
import polars as pl


def _rolling_beta(y: pl.Expr, x: pl.Expr, window: int, min_obs: int) -> pl.Expr:
    ok = y.is_not_null() & x.is_not_null()
    r = lambda e: e.fill_null(0.0).rolling_sum(window, min_samples=1).over("sid")
    n, sx, sy = r(ok.cast(pl.Float64)), r(pl.when(ok).then(x)), r(pl.when(ok).then(y))
    sxy, sxx = r(pl.when(ok).then(x * y)), r(pl.when(ok).then(x * x))
    return pl.when(n >= min_obs).then((n * sxy - sx * sy) / (n * sxx - sx * sx)).otherwise(None)


def dimson_beta(dense: pl.LazyFrame, window: int = 252, min_obs: int = 150) -> pl.LazyFrame:
    """Shrunk Dimson beta per (trade_date, sid) from the dense panel (needs lret and m)."""
    d = dense.with_columns(pl.col("m").shift(1).over("sid").alias("m_lag"))
    b0, b1 = _rolling_beta(pl.col("lret"), pl.col("m"), window, min_obs), _rolling_beta(pl.col("lret"), pl.col("m_lag"), window, min_obs)
    return d.select("trade_date", "sid", (0.6 * (b0 + b1) + 0.4).alias("beta"))


def winsor_z(df: pl.DataFrame, col: str = "raw") -> pl.DataFrame:
    """Per (trade_date, signal): clip at the 1st/99th percentile, then z = (s - mean)/sd."""
    g = ["trade_date", "signal"]
    w = pl.col(col).clip(pl.col(col).quantile(0.01).over(g), pl.col(col).quantile(0.99).over(g))
    return df.with_columns(w.alias("_w")).with_columns(
        ((pl.col("_w") - pl.col("_w").mean().over(g)) / pl.col("_w").std().over(g)).alias("z")).drop("_w")


def neutralize_one_date(z: np.ndarray, sector: np.ndarray, beta: np.ndarray, size: np.ndarray, min_sector: int = 5) -> np.ndarray:
    """Residual of z on sector dummies + beta + size, re-standardized. NaN inputs in beta are filled with 1.0 upstream."""
    sector = np.asarray(sector, dtype=object)
    labels, counts = np.unique(sector, return_counts=True)
    small = set(labels[counts < min_sector])
    sec = np.array(["Unclassified" if s in small else s for s in sector], dtype=object)
    cats = np.unique(sec)
    D = (sec[:, None] == cats[None, :]).astype(float)
    X = np.column_stack([D, beta, size])
    coef, *_ = np.linalg.lstsq(X, z, rcond=None)
    u = z - X @ coef
    sd = u.std(ddof=1)
    return (u - u.mean()) / sd if sd > 0 else np.full_like(u, np.nan)


def neutralize(df: pl.DataFrame, ctx: pl.DataFrame) -> pl.DataFrame:
    """df: (trade_date, sid, signal, z). ctx: (trade_date, sid, industry, beta, size). Adds z_neu."""
    j = df.join(ctx, on=["trade_date", "sid"], how="inner").sort("signal", "trade_date", "sid")  # fixed row order => reproducible lstsq
    j = j.with_columns(pl.col("beta").fill_null(1.0), pl.col("size").fill_null(pl.col("size").median().over("signal", "trade_date")))
    out = []
    for (sig, d), g in j.group_by(["signal", "trade_date"], maintain_order=True):
        if g.height < 30:
            continue
        zn = neutralize_one_date(g["z"].to_numpy(), g["industry"].to_numpy(), g["beta"].to_numpy(), g["size"].to_numpy())
        out.append(g.select("trade_date", "sid", "signal", "z").with_columns(pl.Series("z_neu", zn)))
    return pl.concat(out).filter(pl.col("z_neu").is_not_null() & pl.col("z_neu").is_finite())
