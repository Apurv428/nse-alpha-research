"""Run P0/P1/P2 gross and net on the development window from a walk-forward combo run (PRD sections 8-9).
Reads data only through qr.panel.io (clipped by the OOS lock). Writes runs/portfolios_<ts>/ and logs the two
net books (P1 as active return vs Nifty 500 TRI, P2 as excess return) as trials."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import numpy as np
import polars as pl

from qr.eval import turnover as T
from qr.guard.trial_ledger import git_state, log_trial
from qr.panel import io
from qr.portfolio import capacity as K
from qr.portfolio.backtest import COMPONENTS, attach_universe, build_panel, simulate
from qr.portfolio.metrics import summarize, weekly
from qr.stats.honesty import oos_stats, write

START = dt.date(2017, 1, 2)
TRIPWIRE_IR = 2.0
RF = 0.065   # constant fallback, labelled as such everywhere it is reported (no RBI T-bill file supplied)


def latest_combo(runs: Path = Path("runs")) -> Path:
    c = sorted(Path(runs).glob("combo_*"))
    assert c, "no combo run: run `qr fit` first"
    return c[-1]


def scores_by_date(combo_dir: Path, panel, model: str) -> dict:
    return scores_from_df(pl.read_parquet(combo_dir / "test_scores.parquet").filter(pl.col("model") == model), panel)


def scores_from_df(sc: pl.DataFrame, panel) -> dict:
    """(trade_date, sid, score) -> {trade_date: array over panel.sids} (nan where unscored)."""
    ix = {s: i for i, s in enumerate(panel.sids.tolist())}
    out = {}
    for d, g in sc.group_by("trade_date"):
        a = np.full(len(ix), np.nan)
        for s, v in zip(g["sid"].to_list(), g["score"].to_list()):
            k = ix.get(s)
            if k is not None:
                a[k] = v
        out[d[0]] = a
    return out


def _bench_for(panel, daily):
    ix = {x: i for i, x in enumerate(panel.dates)}
    return np.array([panel.bench_ret[ix[x]] for x in daily["date"].to_list()])[1:]


def run_books(gold=Path("data/gold"), silver=Path("data/silver"), out_root=Path("runs"), combo_dir: Path | None = None,
              sensitivities: bool = True, log: bool = True) -> dict:
    combo_dir = Path(combo_dir) if combo_dir else latest_combo(out_root)
    sel = json.loads((combo_dir / "selection.json").read_text())
    model = sel["headline"]
    prices, cal, bench = io.load_prices(silver), io.load_calendar(silver), io.load_bench(silver)
    universe, fut = io.load_universe(silver), io.load_fut_cont(silver)
    panel = build_panel(prices, cal, bench, universe, fut)
    scores = scores_by_date(combo_dir, panel, model)
    attach_universe(panel, universe, list(scores))
    out = Path(out_root) / f"portfolios_{dt.datetime.now(dt.timezone.utc):%Y%m%dT%H%M%S}"
    out.mkdir(parents=True)
    fwd5 = io.load_gold("fwd_returns", gold).filter(pl.col("h") == 5)
    return evaluate_books(panel, scores, fwd5, cal, bench, out, model, "dev", START, None, sensitivities, log)


def evaluate_books(panel, scores: dict, fwd5: pl.DataFrame, cal: pl.DataFrame, bench: pl.DataFrame, out: Path, model: str, tag: str,
                   first_date, last_date, sensitivities: bool = True, log: bool = True) -> dict:
    """P0/P1/P2 gross and net on [first_date, last_date]; metric keys are `<book>.<tag>.<stat>_<gross|net>`.
    `log` writes the two net books to the trial ledger (development window only)."""
    kw = dict(rf_annual=RF, first_date=first_date, last_date=last_date)
    sha, dirty = git_state()
    metrics, rows = {"git_sha": sha, "git_dirty": dirty, "model": model, "window": [str(first_date), str(last_date)], "rf_annual": RF,
                     "rf_source": "constant fallback 6.5% (no RBI T-bill series supplied)", "tri_is_approx": bool(bench["tri_is_approx"][0])}, []
    wk = T.weekly_dates(cal)
    sc_long = pl.concat([pl.DataFrame({"trade_date": [d] * int(np.isfinite(a).sum()), "sid": panel.sids[np.isfinite(a)], "signal": model, "score": a[np.isfinite(a)]})
                         for d, a in scores.items() if d >= first_date and (last_date is None or d <= last_date)])
    p0 = T.spread_series(T.deciles(sc_long, fwd5, "score", wk)).select("date", "ret")
    metrics["p0.sharpe_gross"] = float(p0["ret"].mean() / p0["ret"].std() * np.sqrt(52))
    metrics["p0.n_weeks"] = p0.height
    p0.write_parquet(out / "p0_weekly.parquet")
    for book in ("P1", "P2"):
        b = book.lower()
        res = {}
        for t_, cm in (("gross", 0.0), ("net", 1.0)):
            o = simulate(panel, scores, book, cost_mult=cm, **kw)
            m = summarize(o["daily"], _bench_for(panel, o["daily"]) if book == "P1" else None, RF)
            res[t_] = (o, m)
            o["daily"].write_parquet(out / f"{b}_{t_}_daily.parquet")
            for k, v in m.items():
                metrics[f"{b}.{tag}.{k}_{t_}"] = v
        o, _ = res["net"]
        metrics[f"{b}.{tag}.turnover_oneway_pa"] = o["turnover_oneway_pa"]
        metrics[f"{b}.{tag}.cap_unfilled_share"] = o["cap_unfilled_share"]
        rows.append({"book": book, **{f"drag_bp_pa_{k}": v for k, v in o["drag_bp_pa"].items()}})
        metrics[f"{b}.{tag}.tripwire"] = bool(tag == "dev" and book == "P1" and res["net"][1]["ir"] > TRIPWIRE_IR)
        d = o["daily"].drop_nulls("ret")
        if book == "P1":
            bb = _bench_for(panel, o["daily"])
            d = d.with_columns(pl.Series("ret", d["ret"].to_numpy() - bb[-d.height:]))
        else:
            d = d.with_columns(pl.col("ret") - RF / 252)
        w = weekly(d)
        w.write_parquet(out / f"{b}_net_weekly_{'active' if book == 'P1' else 'excess'}.parquet")
        if log:
            rec = log_trial("portfolio", {"book": book, "model": model, "enter": 0.10, "keep": 0.20, "cost": "costs.yaml base", "Y": 1.0,
                                          "aum_cr": 1.0, "rf": RF}, (str(w["date"].min()), str(w["date"].max())), "W", w, None, None)
            metrics[f"{b}.{tag}.trial_id"] = rec["trial_id"]
            hon = write(w, out / f"honesty_{b}.json", active=(book == "P1"))   # after logging: N_all includes this trial
            metrics[f"{b}.{tag}.dsr_n_all"] = hon.get("dsr_n_all", {}).get("dsr")
            metrics[f"{b}.{tag}.psr0"] = hon["psr0"]
        else:
            st = oos_stats(w, active=(book == "P1"))
            (out / f"honesty_{b}.json").write_text(json.dumps(st, indent=1, default=str))
            metrics[f"{b}.{tag}.psr0"] = st["psr0"]
        g = K.capacity_grid(panel, scores, book, **kw)
        g.write_csv(out / f"capacity_{b}.csv")
        metrics[f"{b}.capacity"] = K.capacity_from_grid(g)
        metrics[f"{b}.break_even_cost_multiple"] = K.break_even_multiple(panel, scores, book, **kw)
        if sensitivities:
            sens = []
            for name, extra in [("brokerage_0bp", {"brokerage_bp": 0}), ("brokerage_5bp", {"brokerage_bp": 5}), ("Y_0.5", {"Y": 0.5}),
                                ("Y_2.0", {"Y": 2.0}), ("haircut_30pct", {"haircut": 0.3}), ("cost_x2", {"cost_mult": 2.0})]:
                oo = simulate(panel, scores, book, **{**kw, **extra})
                sens.append({"book": book, "case": name, "metric": K.headline_metric(book, K._stat(book, oo, panel, RF)), "cagr": summarize(oo["daily"], None, RF)["cagr"]})
            pl.DataFrame(sens).write_csv(out / f"sensitivities_{b}.csv")
    pl.DataFrame(rows).write_csv(out / "costs.csv")
    (out / "metrics.json").write_text(json.dumps(metrics, indent=1, default=str))
    return {"out": str(out), **metrics}
