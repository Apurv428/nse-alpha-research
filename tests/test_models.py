"""Walk-forward combiners on synthetic gold tables with a planted vs a null relationship."""
import datetime as dt
import json

import numpy as np
import polars as pl
import pytest

from qr.guard import trial_ledger as L
from qr.models.run import run_combine
from qr.signals.registry import REGISTRY

NAMES = list(REGISTRY)


def make_gold(tmp, planted: bool, ns=60, seed=0):
    rng = np.random.default_rng(seed)
    ds, d = [], dt.date(2013, 2, 1)
    while d <= dt.date(2024, 10, 31):
        if d.weekday() < 5:
            ds.append(d)
        d += dt.timedelta(days=1)
    nd = len(ds)
    Z = rng.normal(size=(nd, ns, 8))
    w = np.array([1.0, 1.0, 0.5, 0, 0, 0, 0, 0]) if planted else np.zeros(8)
    signal = 0.012 * (Z @ w)
    base = signal + 0.03 * rng.normal(size=(nd, ns))
    cal = pl.DataFrame({"trade_date": ds, "sess": list(range(nd))}, schema_overrides={"sess": pl.Int64})
    rows = pl.DataFrame({"trade_date": ds}).join(pl.DataFrame({"sid": list(range(1, ns + 1))}), how="cross")  # date-major order
    sig = pl.concat([rows.with_columns(pl.lit(n).alias("signal"), pl.Series("z", Z[:, :, k].ravel()), pl.Series("z_neu", Z[:, :, k].ravel()),
                                       pl.Series("raw", Z[:, :, k].ravel())) for k, n in enumerate(NAMES)])
    fwd = pl.concat([rows.with_columns(pl.lit(h).cast(pl.Int32).alias("h"), pl.Series("fwd_ret", base.ravel() * (h / 5) ** 0.5),
                                       (pl.col("trade_date") + pl.duration(days=h + 4)).alias("label_end_date")) for h in (1, 5, 10, 21)])
    fwd = fwd.with_columns((pl.col("fwd_ret") - pl.col("fwd_ret").mean().over("trade_date", "h")).alias("fwd_ret_xs"))
    ctx = rows.with_columns(pl.lit(1).alias("rank_liq"))
    for name, df in [("signals", sig), ("fwd_returns", fwd), ("context", ctx)]:
        (tmp / "gold" / name).mkdir(parents=True, exist_ok=True)
        df.write_parquet(tmp / "gold" / name / f"{name}.parquet")
    (tmp / "silver" / "calendar").mkdir(parents=True, exist_ok=True)
    cal.write_parquet(tmp / "silver" / "calendar" / "calendar.parquet")


@pytest.mark.parametrize("planted", [True, False])
def test_walk_forward_combiners_and_selection_rule(tmp_path, monkeypatch, planted):
    make_gold(tmp_path, planted)
    monkeypatch.setattr(L, "LEDGER", tmp_path / "trials.jsonl")
    monkeypatch.setattr(L, "RUNS", tmp_path / "runs")
    res = run_combine(tmp_path / "gold", tmp_path / "silver", tmp_path / "runs")
    out = tmp_path / "runs" / res["out"].split("/")[-1]
    s = pl.read_csv(out / "combo_summary.csv")
    assert s.height == 27 and set(s["model"]) == {"EW", "RIDGE", "LGBM"}          # 8 folds x 3 models + 3 pooled rows
    assert s.filter(pl.col("fold_id") != "all").height == 24
    assert L.n_all(tmp_path / "trials.jsonl") == 24                                 # every (model, fold) logged as a trial
    for f in ("combo_decay.csv", "ridge_coefs.csv", "lgbm_importance.csv", "folds.csv", "selection.json", "metrics.json"):
        assert (out / f).exists()
    ic = {m: s.filter((pl.col("model") == m) & (pl.col("fold_id") == "all"))["mean_rank_ic_h5"].item() for m in ("EW", "RIDGE", "LGBM")}
    sel = json.loads((out / "selection.json").read_text())
    if planted:
        assert ic["RIDGE"] > ic["EW"] > 0.02                                       # ridge recovers the true weights, EW dilutes them
        coefs = pl.read_csv(out / "ridge_coefs.csv")
        assert (coefs["coef_MOM_12_1"] > 0).all() and (coefs["coef_REV_5"] > 0).all()
        assert sel["headline"] in ("RIDGE", "LGBM") and sel["candidate_beats_ew"]
    else:
        assert abs(ic["EW"]) < 0.02
        assert sel["headline"] == "EW"                                              # nothing beats equal weight -> EW is the headline
    assert res["combo.fill_rate"]["MOM_12_1"] == 0.0
