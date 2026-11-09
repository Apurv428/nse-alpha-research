"""Hand-built panel with known answers for adjustment, linking, gaps and the jump audit."""
import datetime as dt

import polars as pl
import pytest

from qr.ingest.corpactions import parse_subject
from qr.panel.adjust import assign_events, build_prices, map_events_to_sid
from qr.panel.master import build_security_master, session_calendar

D = dt.date


def _cm(rows):
    return pl.DataFrame(rows, schema={"trade_date": pl.Date, "isin": pl.String, "series": pl.String, "symbol": pl.String,
                                      "close": pl.Float64, "value_inr": pl.Float64}, orient="row").with_columns(
        open=pl.col("close"), high=pl.col("close"), low=pl.col("close"), last=pl.col("close"), prev_close=pl.col("close"),
        volume_sh=pl.lit(1000, pl.Int64), n_trades=pl.lit(10, pl.Int64), src=pl.lit("legacy"))


def days(n, start=D(2021, 10, 25)):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += dt.timedelta(days=1)
    return out


def ca_frame(rows):
    out = []
    for sym, ex, subj in rows:
        p = parse_subject(subj)
        out.append({"symbol": sym, "ex_date": ex, "subject": subj, **p})
    return pl.DataFrame(out, schema_overrides={"a": pl.Float64, "b": pl.Float64, "cash_inr": pl.Float64, "price_factor": pl.Float64})


def run(rows, ca=None):
    cm = _cm(rows)
    cal = session_calendar(cm)
    master, pm = build_security_master(cm, cal, ca)
    ev = None
    if ca is not None:
        ev, _ = map_events_to_sid(ca, master)
    p, audit, st = build_prices(cm, None, pm, cal, ev)
    return master, p, audit, st


def test_irctc_style_split_and_isin_link():
    d = days(6)  # ex-date is d[3]; ISIN changes the same day, as in IRCTC 2021
    rows = [(d[0], "INE1", "EQ", "X", 1000.0, 1e7), (d[1], "INE1", "EQ", "X", 1010.0, 1e7), (d[2], "INE1", "EQ", "X", 1000.0, 1e7),
            (d[3], "INE2", "EQ", "X", 200.0, 1e7), (d[4], "INE2", "EQ", "X", 202.0, 1e7), (d[5], "INE2", "EQ", "X", 202.0, 1e7)]
    ca = ca_frame([("X", d[3], "Face Value Split (Sub-Division) - From Rs 10/- Per Share To Rs 2/- Per Share")])
    master, p, audit, _ = run(rows, ca)
    assert master["sid"].n_unique() == 1  # linked across the ISIN change
    assert "isin_change_same_symbol+corp_action" in master["link_reason"].to_list()
    r = p.sort("trade_date")["ret_1d"].to_list()
    assert r[0] is None
    assert r[3] == pytest.approx(0.0, abs=1e-12)  # 200 / (0.2 * 1000) - 1
    assert audit.height == 0


def test_bonus_infy_style():
    d = days(3)
    rows = [(d[0], "INE1", "EQ", "Y", 1434.25, 1e7), (d[1], "INE1", "EQ", "Y", 717.0, 1e7), (d[2], "INE1", "EQ", "Y", 720.0, 1e7)]
    ca = ca_frame([("Y", d[1], "Bonus 1:1")])
    _, p, audit, _ = run(rows, ca)
    assert p.sort("trade_date")["ret_1d"][1] == pytest.approx(717.0 / (0.5 * 1434.25) - 1)
    assert abs(p.sort("trade_date")["ret_1d"][1]) < 0.20


def test_dividend_adds_to_return_without_price_factor():
    d = days(2)
    rows = [(d[0], "INE1", "EQ", "Z", 100.0, 1e7), (d[1], "INE1", "EQ", "Z", 95.0, 1e7)]
    ca = ca_frame([("Z", d[1], "Dividend - Rs 5 Per Share")])
    _, p, _, _ = run(rows, ca)
    assert p.sort("trade_date")["ret_1d"][1] == pytest.approx((95 + 5) / 100 - 1)


def test_unexplained_jump_is_nulled_and_logged_and_halt_gap_is_kept():
    d = days(12)
    # X: jumps +60% with no action -> nulled. W: stops trading 5 sessions then resumes +60% -> kept (halt gap)
    rows = [(d[i], "INE1", "EQ", "X", 100.0 if i < 5 else 160.0, 1e7) for i in range(12)]
    rows += [(d[i], "INE9", "EQ", "W", 100.0, 1e7) for i in range(4)] + [(d[i], "INE9", "EQ", "W", 160.0, 1e7) for i in range(9, 12)]
    _, p, audit, _ = run(rows)
    x = p.filter(pl.col("symbol") == "X").sort("trade_date")
    assert x["ret_1d"][5] is None
    w = p.filter(pl.col("symbol") == "W").sort("trade_date")
    assert w["gap_days"][4] == 5 and w["ret_1d"][4] == pytest.approx(0.6)
    res = dict(zip(audit["symbol"].to_list(), audit["resolution"].to_list()))
    assert res == {"X": "unexplained_nulled", "W": "halt_gap_kept"}


def test_rights_left_unadjusted_and_big_move_nulled():
    d = days(3)
    rows = [(d[0], "INE1", "EQ", "R", 100.0, 1e7), (d[1], "INE1", "EQ", "R", 60.0, 1e7), (d[2], "INE1", "EQ", "R", 60.0, 1e7)]
    ca = ca_frame([("R", d[1], "Rights 3:16 @ Premium Rs 238/-")])
    _, p, audit, _ = run(rows, ca)
    assert p.sort("trade_date")["ret_1d"][1] is None
    assert audit["resolution"].to_list() == ["unadjusted_event_nulled"]


def test_distinct_listings_with_gap_not_linked():
    d = days(30)
    rows = [(d[i], "INE1", "EQ", "SYM", 10.0, 1e7) for i in range(5)] + [(d[i], "INE2", "EQ", "SYM", 50.0, 1e7) for i in range(20, 25)]
    rows += [(d[i], "INE7", "EQ", "ALWAYS", 10.0, 1e7) for i in range(30)]  # other stocks keep the sessions alive
    master, _, _, _ = run(rows)
    assert master.filter(pl.col("symbol") == "SYM")["sid"].n_unique() == 2  # symbol reused after a long gap = a different company


def test_rename_same_isin_links():
    d = days(6)
    rows = [(d[i], "INE1", "EQ", "OLD", 10.0, 1e7) for i in range(3)] + [(d[i], "INE1", "EQ", "NEW", 10.0, 1e7) for i in range(3, 6)]
    master, p, _, _ = run(rows)
    assert master["sid"].n_unique() == 1 and "rename_same_isin" in master["link_reason"].to_list()


def test_sid_stable_when_future_data_is_added():
    d = days(40)
    base = [(d[i], f"INE{k}", "EQ", f"S{k}", 10.0, 1e7) for k in range(3) for i in range(20)]
    later = base + [(d[i], "INE9", "EQ", "LATE", 10.0, 1e7) for i in range(30, 40)]
    m1, _, _, _ = run(base)
    m2, _, _, _ = run(later)
    a = dict(zip(m1["symbol"], m1["sid"]))
    b = dict(zip(m2["symbol"], m2["sid"]))
    assert all(a[k] == b[k] for k in a)
