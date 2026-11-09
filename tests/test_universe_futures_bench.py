import datetime as dt

import polars as pl
import pytest

from qr.panel.bench import build_bench
from qr.panel.futures import build_fut_cont
from qr.panel.universe import build_universe, month_starts

D = dt.date
CFG = {"universe": {"tradable_series": ["EQ", "BE"], "min_age_sessions": 252, "window": 63, "min_traded_63": 55,
                    "min_close_inr": 10.0, "min_median_value_inr": 10_000_000, "top_n": 2}}


def cal(n=330, start=D(2020, 1, 1)):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += dt.timedelta(days=1)
    return pl.DataFrame({"trade_date": out, "sess": list(range(n))}, schema_overrides={"sess": pl.Int64})


def px(c, spec):
    """spec: sid -> dict(first=sess, last=sess, close=float, value=float, series='EQ', skip=set())"""
    rows = []
    for sid, s in spec.items():
        for i in range(s.get("first", 0), s.get("last", len(c) - 1) + 1):
            if i in s.get("skip", set()):
                continue
            rows.append((sid, i, c["trade_date"][i], s.get("series", "EQ"), s.get("close", 100.0), s.get("value", 5e7), False))
    return pl.DataFrame(rows, schema=["sid", "sess", "trade_date", "series", "close", "value_inr", "has_demerger"], orient="row")


MASTER = pl.DataFrame({"symbol": [], "valid_from": [], "valid_to": [], "sid": []},
                      schema={"symbol": pl.String, "valid_from": pl.Date, "valid_to": pl.Date, "sid": pl.Int64})


def test_universe_filters_and_rank_cap():
    c = cal()
    p = px(c, {1: {"value": 9e7}, 2: {"value": 8e7}, 3: {"value": 7e7},          # three liquid names, cap is 2
               4: {"value": 5e6},                                                   # below Rs 1 crore
               5: {"close": 5.0},                                                   # raw close below Rs 10
               6: {"series": "SM"},                                                 # wrong series
               7: {"first": 200},                                                   # too young
               8: {"skip": set(range(250, 300, 2))}})                               # traded too rarely
    u = build_universe(p, c, None, MASTER, CFG)
    last = u.filter(u["month_start"] == u["month_start"].max())
    assert set(last.filter(pl.col("in_univ"))["sid"].to_list()) == {1, 2}
    assert set(last["sid"].to_list()) == {1, 2, 3}  # only filter-passing names are stored; 3 is ranked out by the cap
    assert last.filter(pl.col("sid") == 3)["in_univ"].item() is False


def test_universe_is_point_in_time_future_data_cannot_change_a_month():
    c = cal()
    spec = {1: {"value": 9e7}, 2: {"value": 8e7}, 3: {"value": 7e7}}
    base = build_universe(px(c, spec), c, None, MASTER, CFG)
    m0 = base["month_start"].max()
    # destroy the future: from the last month on, name 1 goes illiquid and name 3 becomes the best
    spec2 = {1: {"value": 9e7, "last": c.height - 1}, 2: spec[2], 3: spec[3]}
    p2 = px(c, spec2).with_columns(
        pl.when(pl.col("trade_date") >= m0).then(pl.col("value_inr") * 0 + 1.0).otherwise(pl.col("value_inr")).alias("value_inr"))
    alt = build_universe(p2, c, None, MASTER, CFG)
    a = base.filter(pl.col("month_start") == m0).sort("sid").select("sid", "rank_liq", "med_value_63d")
    b = alt.filter(pl.col("month_start") == m0).sort("sid").select("sid", "rank_liq", "med_value_63d")
    assert a.equals(b)  # rows dated on/after the month start never feed that month's universe


def test_month_start_uses_prior_close():
    c = cal(80)
    ms = month_starts(c)
    for r in ms.iter_rows(named=True):
        assert r["asof_date"] < r["month_start"]


def fo_rows(c):
    rows = []
    exp1, exp2 = c["trade_date"][10], c["trade_date"][30]
    for i in range(0, 20):
        t = c["trade_date"][i]
        rows.append((t, "AAA", exp1, 100.0 + i, 100.0 + i, 1, 1e6, 5, 100))
        rows.append((t, "AAA", exp2, 200.0 + i, 200.0 + i, 1, 1e6, 5, 100))
    return pl.DataFrame(rows, schema=["trade_date", "symbol", "expiry", "close", "settle", "contracts", "value_inr", "oi", "lot_size"], orient="row")


def test_futures_roll_three_sessions_before_expiry_and_returns():
    c = cal(40)
    master = pl.DataFrame({"symbol": ["AAA"], "valid_from": [c["trade_date"][0]], "valid_to": [c["trade_date"][39]], "sid": [1]})
    prices = pl.DataFrame({"sid": [1] * 40, "trade_date": c["trade_date"], "price_factor": [1.0] * 40})
    f = build_fut_cont(fo_rows(c), c, master, prices).sort("trade_date")
    exp1, exp2 = c["trade_date"][10], c["trade_date"][30]
    held = dict(zip(f["trade_date"].to_list(), f["expiry_held"].to_list()))
    assert held[c["trade_date"][7]] == exp1      # 3 sessions to expiry: still near month
    assert held[c["trade_date"][8]] == exp2      # fewer than 3: rolled
    r = {d: x for d, x in zip(f["trade_date"].to_list(), f["ret_1d_fut"].to_list())}
    assert r[c["trade_date"][1]] == pytest.approx(101.0 / 100.0 - 1)
    # roll day: return is that of the contract held the day before (expiry 1), not a jump between contracts
    assert r[c["trade_date"][8]] == pytest.approx(108.0 / 107.0 - 1)
    assert f.filter(pl.col("trade_date") == c["trade_date"][8])["roll_flag"].item() is True


def test_bench_tri_formula_and_name_mapping():
    idx = pl.DataFrame({"trade_date": [D(2013, 1, 2), D(2013, 1, 3), D(2013, 1, 4)], "index_name": ["S&P CNX 500", "S&P CNX 500", "Nifty 500"],
                        "close": [100.0, 101.0, 102.0], "pe": [1.0] * 3, "pb": [1.0] * 3, "div_yield_pct": [1.26, 1.26, 1.26]})
    b = build_bench(idx).sort("trade_date")
    assert b["n500_tri"][0] == pytest.approx(100.0)
    assert b["n500_tri"][1] == pytest.approx(100.0 * (101 / 100 + 1.26 / 25200))  # TRI_t uses DY_{t-1}
    assert b["n500_tri"][2] == pytest.approx(b["n500_tri"][1] * (102 / 101 + 1.26 / 25200))
    assert b["tri_is_approx"].all()
