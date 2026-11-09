"""cost_inputs is point-in-time; build_panel/attach_universe wire the tables into the engine's dense arrays."""
import datetime as dt

import numpy as np
import polars as pl

from qr.portfolio.backtest import attach_universe, build_panel
from qr.portfolio.impact import cost_inputs, impact_fraction


def make_prices(T=200, sids=(1, 2), seed=0):
    rng = np.random.default_rng(seed)
    rows, d0 = [], dt.date(2024, 1, 1)
    dates = [d0 + dt.timedelta(days=i) for i in range(T)]
    for s in sids:
        px = 100 * np.cumprod(1 + rng.normal(0, 0.01, T))
        for i in range(T):
            hi, lo = px[i] * (1 + abs(rng.normal(0, 0.005))), px[i] * (1 - abs(rng.normal(0, 0.005)))
            rows.append({"sid": s, "sess": i, "trade_date": dates[i], "high": hi, "low": lo, "close": px[i], "price_factor": 1.0,
                         "ret_1d": None if i == 0 else px[i] / px[i - 1] - 1, "value_inr": 1e7 * (1 + rng.random())})
    cal = pl.DataFrame({"trade_date": dates, "sess": list(range(T))}, schema_overrides={"sess": pl.Int64})
    return pl.DataFrame(rows).with_columns(pl.col("sess").cast(pl.Int64), pl.col("sid").cast(pl.Int64)), cal


def test_cost_inputs_truncation_is_bit_identical():
    px, cal = make_prices()
    full = cost_inputs(px, cal)
    cut = 150
    part = cost_inputs(px.filter(pl.col("sess") <= cut), cal.filter(pl.col("sess") <= cut))
    a = full.filter(pl.col("sess") <= cut).sort("sid", "sess")
    b = part.sort("sid", "sess")
    for c in ("half_spread", "sigma", "adv"):
        assert a[c].to_list() == b[c].to_list(), c          # no value at t depends on rows after t


def test_half_spread_floor_cap_and_sigma_adv_ranges():
    px, cal = make_prices()
    o = cost_inputs(px, cal).drop_nulls()
    assert o["half_spread"].min() >= 2e-4 - 1e-12 and o["half_spread"].max() <= 50e-4 + 1e-12
    assert (o["sigma"] > 0).all() and (o["adv"] > 0).all()


def test_impact_square_root_law():
    f = impact_fraction(np.array([0.02]), np.array([1e6]), np.array([1e8]), 1.0)[0]
    assert abs(f - 0.02 * 0.1) < 1e-12
    assert abs(impact_fraction(np.array([0.02]), np.array([4e6]), np.array([1e8]), 1.0)[0] - 2 * f) < 1e-12   # 4x size -> 2x impact
    assert impact_fraction(np.array([0.02]), np.array([1e6]), np.array([0.0]), 1.0)[0] == 0.0


def test_build_panel_and_attach_universe_alignment():
    px, cal = make_prices()
    ci = cost_inputs(px, cal)
    bench = pl.DataFrame({"trade_date": cal["trade_date"], "n500_tri": np.linspace(100, 120, cal.height), "tri_is_approx": True})
    uni = pl.DataFrame({"month_start": [dt.date(2024, 1, 1)] * 2 + [dt.date(2024, 4, 1)], "sid": [1, 2, 1], "in_univ": [True, True, True],
                        "in_fno": [False, True, True]})
    fut = pl.DataFrame({"sid": [1], "sess": [10], "ret_1d_fut": [0.01], "roll_flag": [True]}, schema_overrides={"sid": pl.Int64, "sess": pl.Int64})
    P = build_panel(px, cal, bench, uni, fut, ci)
    assert P.ret.shape == (200, 2) and np.isnan(P.ret[0]).all()
    assert P.fret[10, 0] == 0.01 and P.froll[10, 0] and not P.froll[11, 0]
    attach_universe(P, uni, [dt.date(2024, 2, 15), dt.date(2024, 5, 1)])
    assert P.univ[dt.date(2024, 2, 15)][1].tolist() == [False, True]    # uses the January membership
    assert P.univ[dt.date(2024, 5, 1)][1].tolist() == [True, False]     # April: sid 2 not listed -> False
