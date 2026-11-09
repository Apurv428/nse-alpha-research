"""`qr eval`: single-signal evaluation, raw (z) and neutral (z_neu), on the development window (PRD section 6).

Outputs under runs/eval_<ts>/ : ic_summary.csv (64 rows), holm.csv, decay.csv, decay_marginal.csv, turnover.csv,
corr_scores.csv, corr_ic.csv, deciles.csv, ic_by_regime.csv, metrics.json. Each (signal, version) is logged as a
trial BEFORE any number is printed.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import polars as pl

from qr.eval import decay as D
from qr.eval import ic as I
from qr.eval import turnover as T
from qr.guard.trial_ledger import log_trial
from qr.panel import io
from qr.signals.registry import REGISTRY, dense_panel

TRIPWIRE_RANK_IC = 0.08  # PRD section 11: stop and audit for leakage above this at h = 5
VERSIONS = {"raw": "z", "neutral": "z_neu"}


def run_eval(gold: Path = Path("data/gold"), silver: Path = Path("data/silver"), out_root: Path = Path("runs"),
             marginal: bool = True) -> dict:
    sig = io.load_gold("signals", gold)
    fwd = io.load_gold("fwd_returns", gold)
    ctx = io.load_gold("context", gold)
    cal, bench = io.load_calendar(silver), io.load_bench(silver)
    out = Path(out_root) / f"eval_{dt.datetime.now(dt.timezone.utc):%Y%m%dT%H%M%S}"
    out.mkdir(parents=True, exist_ok=True)
    wk = T.weekly_dates(cal)
    fwd5 = fwd.filter(pl.col("h") == 5)
    summaries, ics_by_v, spreads, dec_tables, turn, auto, mdecay, c_scores, c_ic, regime = [], {}, {}, [], [], [], [], [], [], []
    for ver, col in VERSIONS.items():
        s = sig.filter(pl.col(col).is_not_null())
        ics = I.ic_series(s, fwd, col)
        ics_by_v[ver] = ics
        summaries.append(I.summarize(ics, ver))
        dec = T.deciles(s, fwd5, col, wk)
        sp = T.spread_series(dec)
        spreads[ver] = sp
        dec_tables.append(T.decile_table(dec, sp).with_columns(pl.lit(ver).alias("version")))
        turn.append(T.top_decile_turnover(s, col, wk).join(T.signal_autocorr(s, col, cal), on="signal").with_columns(pl.lit(ver).alias("version")))
        c_scores.append(D.corr_scores(s, col).with_columns(pl.lit(ver).alias("version")))
        c_ic.append(D.corr_ic(ics).with_columns(pl.lit(ver).alias("version")))
        regime.append(D.stability(s, col, fwd5, ctx, bench, cal).with_columns(pl.lit(ver).alias("version")))
    summary = pl.concat(summaries)
    assert summary.height == len(REGISTRY) * 2 * 4, f"ic_summary must have 64 rows, has {summary.height}"
    holm = I.holm_table(summary)
    # ---- log every (signal, version) as a trial BEFORE anything is printed ----
    trial_ids = {}
    for ver in VERSIONS:
        for name in REGISTRY:
            r5 = summary.filter((pl.col("signal") == name) & (pl.col("version") == ver) & (pl.col("h") == 5)).row(0, named=True)
            sp = spreads[ver].filter(pl.col("signal") == name).select("date", "ret")
            rec = log_trial("signal", {"signal": name, "version": ver, "horizon": 5, "decile_spread": "D10-D1 weekly"},
                            (str(sig["trade_date"].min()), str(sig["trade_date"].max())), "W", sp, r5["mean_rank_ic"], r5["t_nw"])
            trial_ids[(name, ver)] = rec["trial_id"]
    summary.write_csv(out / "ic_summary.csv")
    holm.write_csv(out / "holm.csv")
    summary.filter(pl.col("h").is_in([1, 5, 10, 21])).pivot(on="h", index=["signal", "version"], values="mean_rank_ic").write_csv(out / "decay.csv")
    pl.concat(turn).write_csv(out / "turnover.csv")
    pl.concat(c_scores).write_csv(out / "corr_scores.csv")
    pl.concat(c_ic).write_csv(out / "corr_ic.csv")
    pl.concat(dec_tables).write_csv(out / "deciles.csv")
    pl.concat(regime).write_csv(out / "ic_by_regime.csv")
    for ver in VERSIONS:
        ics_by_v[ver].write_parquet(out / f"daily_ic_{ver}.parquet")
    if marginal:
        mr = D.marginal_returns(dense_panel(io.load_prices(silver), cal, bench))
        pl.concat([D.marginal_decay(sig.filter(pl.col(c).is_not_null()), c, mr).with_columns(pl.lit(v).alias("version")) for v, c in VERSIONS.items()]).write_csv(out / "decay_marginal.csv")
    # ---- headline metrics (flat keys; the ledger renders RESULTS.md from this file) ----
    neu5 = summary.filter((pl.col("version") == "neutral") & (pl.col("h") == 5))
    best = neu5.sort("t_nw", descending=True).row(0, named=True)
    m = {"sig.best_neu.name": best["signal"], "sig.best_neu.rank_ic_h5": best["mean_rank_ic"], "sig.best_neu.t_nw_h5": best["t_nw"],
         "sig.n_pass_holm_t3": int(holm["pass_holm_t3"].sum()), "sig.n_sig_wrong_sign": int(holm["sig_wrong_sign"].sum()),
         "sig.max_rank_ic_h5": float(summary.filter(pl.col("h") == 5)["mean_rank_ic"].max()),
         "sig.tripwire_hit": bool(summary.filter(pl.col("h") == 5)["mean_rank_ic"].max() > TRIPWIRE_RANK_IC),
         "sig.n_dates": int(summary["n_dates"].max()), "trial_ids": {f"{a}|{b}": v for (a, b), v in trial_ids.items()}}
    (out / "metrics.json").write_text(json.dumps(m, indent=1, default=str))
    return {"out": str(out), **m}
