"""Synthetic end-to-end check of silver -> gold -> eval plumbing, and of the IC machinery on a planted effect."""
import datetime as dt
import json

import numpy as np
import polars as pl
import pytest

from qr.eval import ic as I
from qr.eval import turnover as T
from qr.guard import trial_ledger as L


def test_ic_machinery_detects_planted_effect_and_not_noise():
    rng = np.random.default_rng(0)
    nd, ns = 400, 120
    dates = [dt.date(2018, 1, 1) + dt.timedelta(days=i) for i in range(nd)]
    z = rng.normal(size=(nd, ns))
    noise = rng.normal(size=(nd, ns))
    rows = []
    for i, d in enumerate(dates):
        for j in range(ns):
            rows.append((d, j, "PLANT", z[i, j], 0.01 * z[i, j] + 0.02 * noise[i, j], "NOISE_SIG", rng.normal()))
    df = pl.DataFrame(rows, schema=["trade_date", "sid", "signal", "z", "fwd_ret", "n2", "z2"], orient="row")
    scores = pl.concat([df.select("trade_date", "sid", "signal", "z"),
                        df.select("trade_date", "sid", pl.lit("NOISE").alias("signal"), pl.col("z2").alias("z"))])
    fwd = df.select("trade_date", "sid", pl.lit(5).alias("h"), "fwd_ret").unique(["trade_date", "sid"])
    ics = I.ic_series(scores, fwd, "z")
    s = I.summarize(ics, "raw")
    plant = s.filter(pl.col("signal") == "PLANT").row(0, named=True)
    noise_ = s.filter(pl.col("signal") == "NOISE").row(0, named=True)
    assert plant["mean_rank_ic"] > 0.2 and plant["t_nw"] > 10 and plant["hit_rate"] > 0.95
    assert abs(noise_["t_nw"]) < 3.0
    assert plant["n_dates"] == nd
    # deciles are monotone for the planted signal and the D10-D1 spread is positive
    wk = pl.DataFrame({"trade_date": dates[::5]})
    dec = T.deciles(scores.filter(pl.col("signal") == "PLANT"), fwd.with_columns(pl.col("fwd_ret")), "z", wk)
    sp = T.spread_series(dec)
    tab = T.decile_table(dec, sp)
    assert tab["monotonicity"][0] > 0.9 and tab["spread_mean_weekly"][0] > 0


def test_holm_adjust_matches_known_values():
    p = np.array([0.01, 0.04, 0.03, 0.005])
    adj = I.holm_adjust(p)
    # sorted p: .005 .01 .03 .04 -> *4,*3,*2,*1 = .02 .03 .06 .04 -> cummax .02 .03 .06 .06
    assert adj == pytest.approx([0.03, 0.06, 0.06, 0.02])


def test_turnover_of_a_static_top_decile_is_zero_and_full_rotation_is_one():
    d = [dt.date(2020, 1, 3) + dt.timedelta(days=7 * i) for i in range(4)]
    rows = []
    for k, t in enumerate(d):
        for sid in range(100):
            same = sid  # static ranking
            flip = sid if k % 2 == 0 else 99 - sid  # top decile alternates between two disjoint sets
            rows.append((t, sid, "STATIC", float(same)))
            rows.append((t, sid, "FLIP", float(flip)))
    s = pl.DataFrame(rows, schema=["trade_date", "sid", "signal", "z"], orient="row")
    out = T.top_decile_turnover(s, "z", pl.DataFrame({"trade_date": d})).sort("signal")
    got = dict(zip(out["signal"], out["mean_turnover"]))
    assert got["STATIC"] == pytest.approx(0.0) and got["FLIP"] == pytest.approx(1.0)
