"""Signal unit tests on hand-built 3-stock, 300-day panels with known answers + synthetic PIT truncation."""
import datetime as dt
import math

import numpy as np
import polars as pl
import pytest

from qr.signals import registry as R

N = 300


def dates(n=N):
    out, d = [], dt.date(2020, 1, 1)
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += dt.timedelta(days=1)
    return out


def build(seed=0, n=N):
    rng = np.random.default_rng(seed)
    ds = dates(n)
    cal = pl.DataFrame({"trade_date": ds, "sess": list(range(n))}, schema_overrides={"sess": pl.Int64})
    m = rng.normal(0, 0.01, n)
    m[0] = 0.0
    close = 1000 * np.exp(np.cumsum(m))
    bench = pl.DataFrame({"trade_date": ds, "n500_close": close})
    eps = rng.normal(0, 0.02, n)
    A = np.full(n, 0.001)
    B = np.where(np.arange(n) % 2 == 0, 0.01, -0.01)
    C = np.exp(1.5 * m + eps) - 1
    rows = []
    for sid, r, v, d in [(1, A, 1e8, 50.0), (2, B, 5e7, 40.0), (3, C, 2e7, 30.0)]:
        for i in range(n):
            rows.append((sid, i, float(r[i]) if i > 0 else None, v, d))
    px = pl.DataFrame(rows, schema=["sid", "sess", "ret_1d", "value_inr", "deliv_pct"], orient="row")
    return px, cal, bench, m, eps


def sig(name, px, cal, bench):
    d = R.dense_panel(px, cal, bench)
    return R.compute_all(d, [name])


def at(df, sid, sess_idx, cal):
    t = cal["trade_date"][sess_idx]
    r = df.filter((pl.col("sid") == sid) & (pl.col("trade_date") == t))
    return r["raw"].item() if r.height else None


def test_known_answers_constant_return_stock():
    px, cal, bench, m, eps = build()
    t = 280
    assert at(sig("MOM_12_1", px, cal, bench), 1, t, cal) == pytest.approx(231 * math.log(1.001))
    assert at(sig("REV_5", px, cal, bench), 1, t, cal) == pytest.approx(-5 * math.log(1.001))
    assert at(sig("LOWVOL_63", px, cal, bench), 1, t, cal) == pytest.approx(0.0, abs=1e-12)
    assert at(sig("AMIHUD_63", px, cal, bench), 1, t, cal) == pytest.approx(math.log(0.001 / 10.0))
    assert at(sig("ABVOL_5_63", px, cal, bench), 1, t, cal) == pytest.approx(0.0, abs=1e-12)
    assert at(sig("DELIV_ABN", px, cal, bench), 1, t, cal) == pytest.approx(0.0, abs=1e-12)
    assert at(sig("HIGH52", px, cal, bench), 1, t, cal) == pytest.approx(1.0)


def test_alternating_stock_lowvol_and_rev():
    px, cal, bench, *_ = build()
    t = 280
    l = np.array([math.log(1.01) if i % 2 == 0 else math.log(0.99) for i in range(N)])
    assert at(sig("LOWVOL_63", px, cal, bench), 2, t, cal) == pytest.approx(-l[t - 62:t + 1].std(ddof=1))
    assert at(sig("REV_5", px, cal, bench), 2, t, cal) == pytest.approx(-l[t - 4:t + 1].sum())
    assert at(sig("MOM_12_1", px, cal, bench), 2, t, cal) == pytest.approx(l[t - 251:t - 20].sum())


def test_ivol_equals_numpy_residual_sd_and_recovers_noise_scale():
    px, cal, bench, m, eps = build()
    t = 280
    lret = np.log1p(px.filter(pl.col("sid") == 3).sort("sess")["ret_1d"].fill_null(0.0).to_numpy())
    mk = np.log(bench["n500_close"].to_numpy()[1:] / bench["n500_close"].to_numpy()[:-1])
    mk = np.concatenate([[np.nan], mk])
    sl = slice(t - 62, t + 1)
    X = np.column_stack([np.ones(63), mk[sl]])
    y = lret[sl]
    coef, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ coef
    expected = -math.sqrt((resid ** 2).sum() / (63 - 2))
    assert at(sig("IVOL_63", px, cal, bench), 3, t, cal) == pytest.approx(expected, rel=1e-6)
    assert -at(sig("IVOL_63", px, cal, bench), 3, t, cal) == pytest.approx(0.02, rel=0.3)  # true idiosyncratic sd


def test_min_obs_and_missing_session_is_not_zero():
    px, cal, bench, *_ = build()
    t = 280
    # drop 3 of the last 5 sessions for stock 2 -> REV_5 needs 4 of 5 -> undefined; drop 1 -> defined on 4 obs
    miss3 = px.filter(~((pl.col("sid") == 2) & pl.col("sess").is_in([t, t - 1, t - 2])))
    assert at(sig("REV_5", miss3, cal, bench), 2, t - 3, cal) is not None
    assert at(sig("REV_5", miss3, cal, bench), 2, t, cal) is None  # not traded at t -> no signal row at t
    miss1 = px.filter(~((pl.col("sid") == 2) & (pl.col("sess") == t - 1)))
    l = [math.log(1.01) if i % 2 == 0 else math.log(0.99) for i in range(N)]
    exp = -(sum(l[t - 4:t + 1]) - l[t - 1])  # sum over the 4 valid observations
    assert at(sig("REV_5", miss1, cal, bench), 2, t, cal) == pytest.approx(exp)
    # a 10-session halt is a 10-session gap, not 1 day: MOM window still counts sessions
    halt = px.filter(~((pl.col("sid") == 1) & pl.col("sess").is_between(100, 109)))
    d = R.dense_panel(halt, cal, bench).collect().filter(pl.col("sid") == 1)
    assert d.height == N and d.filter(pl.col("sess").is_between(100, 109))["lret"].null_count() == 10


@pytest.mark.parametrize("name", list(R.REGISTRY))
def test_every_signal_is_point_in_time_under_truncation(name):
    """Values dated <= c are bit-identical whether or not data after c exists (property test on random gappy panels)."""
    rng = np.random.default_rng(4)
    px, cal, bench, *_ = build(seed=9)
    keep = rng.random(px.height) > 0.04  # random missing sessions
    px = px.filter(pl.Series(keep))
    full = sig(name, px, cal, bench)
    for c in (150, 220, 270):
        cal_c = cal.filter(pl.col("sess") <= c)
        trunc = sig(name, px.filter(pl.col("sess") <= c), cal_c, bench.filter(pl.col("trade_date") <= cal_c["trade_date"].max()))
        a = full.filter(pl.col("trade_date") <= cal_c["trade_date"].max()).sort("sid", "trade_date")
        b = trunc.sort("sid", "trade_date")
        assert a.equals(b), f"{name} changed under truncation at {c}"


def test_registry_has_eight_signals_with_preregistered_signs():
    assert set(R.REGISTRY) == {"MOM_12_1", "REV_5", "LOWVOL_63", "IVOL_63", "AMIHUD_63", "ABVOL_5_63", "DELIV_ABN", "HIGH52"}
    assert all(v["sign"] == +1 for v in R.REGISTRY.values())  # all oriented so higher = higher expected return
    assert (R.REGISTRY["MOM_12_1"]["window"], R.REGISTRY["MOM_12_1"]["min_obs"]) == (231, 200)
