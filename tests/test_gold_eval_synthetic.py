"""Synthetic silver -> gold -> eval run: plumbing, 64-row IC table, trial logging, no-leak on future rows."""
import datetime as dt
import json

import numpy as np
import polars as pl
import pytest

from qr.eval.run import run_eval
from qr.guard import trial_ledger as L
from qr.panel.universe import build_universe
from qr.signals.gold import build_gold

CFG = {"universe": {"tradable_series": ["EQ", "BE"], "min_age_sessions": 252, "window": 63, "min_traded_63": 55,
                    "min_close_inr": 10.0, "min_median_value_inr": 10_000_000, "top_n": 60}}


def make_silver(root, n=900, ns=80, seed=0, last_date_override=None):
    rng = np.random.default_rng(seed)
    ds, d = [], dt.date(2018, 1, 1)
    while len(ds) < n:
        if d.weekday() < 5:
            ds.append(d)
        d += dt.timedelta(days=1)
    cal = pl.DataFrame({"trade_date": ds, "sess": list(range(n))}, schema_overrides={"sess": pl.Int64})
    m = rng.normal(0.0004, 0.01, n)
    m[0] = 0
    bench = pl.DataFrame({"trade_date": ds, "n500_close": 1000 * np.exp(np.cumsum(m)), "n500_tri": 1000 * np.exp(np.cumsum(m)),
                          "tri_is_approx": [True] * n, "div_yield_pct": [1.2] * n})
    rows = []
    for sid in range(1, ns + 1):
        beta = rng.uniform(0.5, 1.5)
        eps = rng.normal(0, 0.015, n)
        close = 100.0
        val = rng.uniform(3e7, 3e8)
        for i in range(n):
            if rng.random() < 0.02:
                continue  # missing session
            r = beta * m[i] + eps[i]
            close *= np.exp(r)
            rows.append((ds[i], sid, f"S{sid}", f"INE{sid}", "EQ", close, val * rng.uniform(0.7, 1.3), float(np.expm1(r)) if i else None,
                         float(rng.uniform(30, 60)), i, False))
    px = pl.DataFrame(rows, schema=["trade_date", "sid", "symbol", "isin", "series", "close", "value_inr", "ret_1d", "deliv_pct", "sess", "has_demerger"],
                      orient="row")
    master = pl.DataFrame({"symbol": [f"S{s}" for s in range(1, ns + 1)], "valid_from": [ds[0]] * ns, "valid_to": [ds[-1]] * ns, "sid": list(range(1, ns + 1))})
    uni = build_universe(px, cal, None, master, CFG)
    sectors = pl.DataFrame({"sid": list(range(1, ns + 1)), "industry": [f"I{s % 6}" for s in range(ns)], "source_file": ["x"] * ns, "snapshot_date": [None] * ns},
                           schema_overrides={"snapshot_date": pl.String})
    for name, df, part in [("calendar", cal, False), ("bench", bench, False), ("universe", uni, False), ("sectors", sectors, False)]:
        (root / name).mkdir(parents=True, exist_ok=True)
        df.write_parquet(root / name / f"{name}.parquet")
    (root / "prices").mkdir(parents=True, exist_ok=True)
    for (y,), g in px.with_columns(pl.col("trade_date").dt.year().alias("y")).group_by("y"):
        g.drop("y").write_parquet(root / "prices" / f"year={y}.parquet")
    return px, uni


@pytest.fixture(scope="module")
def pipeline(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("synth")
    silver, gold, runs = tmp / "silver", tmp / "gold", tmp / "runs"
    make_silver(silver)
    mp = pytest.MonkeyPatch()
    mp.setattr(L, "LEDGER", tmp / "trials.jsonl")
    mp.setattr(L, "RUNS", runs)
    man = build_gold(silver, gold)
    res = run_eval(gold, silver, runs)
    yield tmp, man, res
    mp.undo()


def test_gold_tables_and_universe_membership(pipeline):
    tmp, man, res = pipeline
    sig = pl.read_parquet(tmp / "gold" / "signals" / "signals.parquet")
    assert set(sig["signal"].unique()) == {"MOM_12_1", "REV_5", "LOWVOL_63", "IVOL_63", "AMIHUD_63", "ABVOL_5_63", "DELIV_ABN", "HIGH52"}
    per_day = sig.filter(pl.col("signal") == "REV_5").group_by("trade_date").agg(n=pl.len())
    assert per_day["n"].max() <= 60  # the rank cap
    z = sig.group_by("trade_date", "signal").agg(m=pl.col("z").mean(), s=pl.col("z").std())
    assert z["m"].abs().max() < 1e-9 and (z["s"] - 1).abs().max() < 1e-6
    zn = sig.filter(pl.col("z_neu").is_not_null()).group_by("trade_date", "signal").agg(m=pl.col("z_neu").mean(), s=pl.col("z_neu").std())
    assert zn["m"].abs().max() < 1e-9 and (zn["s"] - 1).abs().max() < 1e-6
    fwd = pl.read_parquet(tmp / "gold" / "fwd_returns" / "fwd_returns.parquet")
    assert set(fwd["h"].unique()) == {1, 5, 10, 21}
    assert (fwd["label_end_date"] > fwd["trade_date"]).all()


def test_forward_return_matches_hand_computation(pipeline):
    tmp, *_ = pipeline
    silver = tmp / "silver"
    px = pl.read_parquet(silver / "prices").sort("sid", "sess") if False else pl.concat([pl.read_parquet(f) for f in sorted((silver / "prices").glob("*.parquet"))]).sort("sid", "sess")
    fwd = pl.read_parquet(tmp / "gold" / "fwd_returns" / "fwd_returns.parquet").filter(pl.col("h") == 5).sort("sid", "trade_date")
    row = fwd.row(500, named=True)
    s = px.filter(pl.col("sid") == row["sid"]).sort("sess")
    t = s.filter(pl.col("trade_date") == row["trade_date"])["sess"].item()
    window = s.filter(pl.col("sess").is_between(t + 2, t + 6))["ret_1d"].to_numpy()   # sessions t+2 .. t+1+h
    assert row["fwd_ret"] == pytest.approx(float(np.prod(1 + window) - 1), rel=1e-9)  # fill at close t+1, exit at close t+6


def test_eval_outputs_64_rows_and_16_trials_logged_before_print(pipeline):
    tmp, man, res = pipeline
    out = tmp / "runs" / res["out"].split("/")[-1]
    s = pl.read_csv(out / "ic_summary.csv")
    assert s.height == 64 and {"n_dates", "t_nw"} <= set(s.columns)
    for f in ("holm.csv", "decay.csv", "decay_marginal.csv", "turnover.csv", "corr_scores.csv", "corr_ic.csv", "deciles.csv", "ic_by_regime.csv", "metrics.json"):
        assert (out / f).exists(), f
    assert L.n_all(tmp / "trials.jsonl") == 16
    t = L.load_trials(tmp / "trials.jsonl")[0]
    assert t["kind"] == "signal" and t["freq"] == "W" and t["n_obs"] > 20
    # random data: no signal should look real, and the tripwire must stay off
    assert res["sig.tripwire_hit"] is False
    assert s.filter((pl.col("h") == 5))["t_nw"].abs().max() < 4.5
    assert json.loads((out / "metrics.json").read_text())["sig.n_pass_holm_t3"] <= 1


def test_future_rows_cannot_change_gold_values_before_them(tmp_path):
    """Truncation property end-to-end: rebuild silver from data cut at c; gold signal values dated <= c are identical."""
    full_dir, cut_dir = tmp_path / "full", tmp_path / "cut"
    px, uni = make_silver(full_dir / "silver")
    c = px.filter(pl.col("sess") == 700)["trade_date"][0]
    # cut silver: drop prices and calendar/bench after c, rebuild the universe from the truncated prices
    cut_silver = cut_dir / "silver"
    px_c = px.filter(pl.col("trade_date") <= c)
    cal = pl.read_parquet(full_dir / "silver" / "calendar" / "calendar.parquet").filter(pl.col("trade_date") <= c)
    bench = pl.read_parquet(full_dir / "silver" / "bench" / "bench.parquet").filter(pl.col("trade_date") <= c)
    master = pl.DataFrame({"symbol": [f"S{s}" for s in range(1, 81)], "valid_from": [cal["trade_date"][0]] * 80, "valid_to": [c] * 80, "sid": list(range(1, 81))})
    uni_c = build_universe(px_c, cal, None, master, CFG)
    for name, df in [("calendar", cal), ("bench", bench), ("universe", uni_c), ("sectors", pl.read_parquet(full_dir / "silver" / "sectors" / "sectors.parquet"))]:
        (cut_silver / name).mkdir(parents=True, exist_ok=True)
        df.write_parquet(cut_silver / name / f"{name}.parquet")
    (cut_silver / "prices").mkdir(parents=True, exist_ok=True)
    for (y,), g in px_c.with_columns(pl.col("trade_date").dt.year().alias("y")).group_by("y"):
        g.drop("y").write_parquet(cut_silver / "prices" / f"year={y}.parquet")
    build_gold(full_dir / "silver", full_dir / "gold")
    build_gold(cut_silver, cut_dir / "gold")
    a = pl.read_parquet(full_dir / "gold" / "signals" / "signals.parquet").filter(pl.col("trade_date") <= c).sort("trade_date", "sid", "signal")
    b = pl.read_parquet(cut_dir / "gold" / "signals" / "signals.parquet").sort("trade_date", "sid", "signal")
    assert a.height == b.height and a.height > 1000
    assert a.select("trade_date", "sid", "signal", "raw", "z", "z_neu").equals(b.select("trade_date", "sid", "signal", "raw", "z", "z_neu"))
