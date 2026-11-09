"""Day 1 gate checks -> runs/data_qa/gate_report.json (every Day 1 number in RESULTS.md comes from here).

Counts and audit only. No return statistics are computed on rows after dev_end (PRD s9.2).
"""
from __future__ import annotations

import json
from pathlib import Path

import polars as pl
import yaml

ROOT = Path(__file__).resolve().parents[3]
CFG = yaml.safe_load((ROOT / "config" / "research.yaml").read_text())
DEV_END = CFG["dev"]["end"]


def _prices(silver: Path) -> pl.LazyFrame:
    return pl.scan_parquet(silver / "prices" / "year=*.parquet")


def run_qa(silver: Path = Path("data/silver"), qa: Path = Path("runs/data_qa"), n_events: int = 20) -> dict:
    silver, qa = Path(silver), Path(qa)
    rep: dict = {}
    cal = pl.read_parquet(silver / "calendar" / "calendar.parquet")
    # 1. sessions per year (full calendar years only; first and last sample years may be partial)
    spy = cal.with_columns(pl.col("trade_date").dt.year().alias("year")).group_by("year").agg(n=pl.len()).sort("year")
    first_y, last_y = cal["trade_date"].min().year, cal["trade_date"].max().year
    rep["sessions_per_year"] = dict(zip(spy["year"].to_list(), spy["n"].to_list()))
    full = spy.filter((pl.col("year") > first_y) & (pl.col("year") < last_y))
    bad = full.filter(~pl.col("n").is_between(245, 252))
    rep["sessions_per_year_out_of_range"] = dict(zip(bad["year"].to_list(), bad["n"].to_list()))
    rep["gate_sessions_245_252"] = bad.height == 0
    rep["n_sessions"] = cal.height

    master = pl.read_parquet(silver / "security_master" / "security_master.parquet")
    rep["n_sids"] = master["sid"].n_unique()
    uni = pl.read_parquet(silver / "universe" / "universe.parquet")
    inu = uni.filter(pl.col("in_univ"))
    per_month = inu.group_by("month_start").agg(n=pl.len()).sort("month_start")
    dev = per_month.filter(pl.col("month_start") >= pl.lit(CFG["dev"]["start"]).str.to_date())
    rep["universe_names_per_month"] = {"min": int(dev["n"].min()) if dev.height else None,
                                       "max": int(dev["n"].max()) if dev.height else None,
                                       "months_below_750": int((dev["n"] < 750).sum()) if dev.height else None,
                                       "n_months": dev.height}
    rep["gate_universe_750"] = bool(dev.height and (dev["n"] == CFG["universe"]["top_n"]).all())
    p = _prices(silver)
    last_sess_all = int(cal["sess"].max())
    ever = inu.select("sid").unique()
    ls = p.group_by("sid").agg(last_sess=pl.col("sess").max(), last_date=pl.col("trade_date").max()).collect()
    dl = ever.join(ls, on="sid").filter(pl.col("last_sess") < last_sess_all - 63)
    rep["n_sids_ever_in_universe"] = ever.height
    rep["n_delisted_in_univ"] = dl.height  # last trade > 63 sessions before the end of the sample
    # 2. jump audit: every flag on an ever-in-universe name has a resolution
    audit = pl.read_csv(qa / "jump_audit.csv", try_parse_dates=True)
    ever_audit = audit.join(ever, on="sid")
    rep["jump_audit"] = {"n_flagged_all": audit.height, "n_flagged_ever_in_univ": ever_audit.height,
                         "unresolved_ever_in_univ": int(ever_audit["resolution"].is_null().sum()),
                         "by_resolution_ever_in_univ": dict(zip(*[ever_audit["resolution"].value_counts()[c].to_list() for c in ("resolution", "count")])) if ever_audit.height else {}}
    rep["gate_jumps_resolved"] = rep["jump_audit"]["unresolved_ever_in_univ"] == 0
    # 3. corporate-action ex-date spot check: most liquid split/bonus events inside the development window
    ca_dir = Path("data/raw/corpactions")
    if list(ca_dir.glob("*.csv")):
        from qr.ingest.corpactions import build_corp_actions
        from qr.panel.adjust import map_events_to_sid

        ca = build_corp_actions(ca_dir).filter(pl.col("action").is_in(["split", "bonus"]) & (pl.col("ex_date") <= pl.lit(DEV_END).str.to_date()))
        ev, _ = map_events_to_sid(ca, master)
        ev = ev.join(p.select("sid", "trade_date", "value_inr", "ret_1d", "price_factor").collect(),
                     left_on=["sid", "ex_date"], right_on=["sid", "trade_date"], how="inner")
        top = ev.filter(pl.col("price_factor") != 1.0).sort("value_inr", descending=True).head(n_events)
        rep["corp_action_spot_check"] = {
            "n_checked": top.height,
            "events": top.select("symbol", "ex_date", "action", "price_factor", "ret_1d").to_dicts(),
            "max_abs_ret_on_exdate": float(top["ret_1d"].abs().max()) if top.height else None,
            "n_null_ret": int(top["ret_1d"].is_null().sum()),
            "n_ge_20pct": int((top["ret_1d"].abs() >= 0.20).sum())}
        rep["gate_actions_lt_20pct"] = bool(top.height >= n_events and rep["corp_action_spot_check"]["n_ge_20pct"] == 0
                                            and rep["corp_action_spot_check"]["n_null_ret"] == 0)
    else:
        rep["corp_action_spot_check"] = "not run: no corporate-action export in data/raw/corpactions"
        rep["gate_actions_lt_20pct"] = False
    # 4. Unclassified share per year (sector labels are a 2026 snapshot)
    sec = pl.read_parquet(silver / "sectors" / "sectors.parquet")
    um = inu.join(sec, on="sid", how="left").with_columns(pl.col("month_start").dt.year().alias("year"))
    uc = um.group_by("year").agg(share_unclassified=(pl.col("industry") == "Unclassified").mean()).sort("year")
    rep["unclassified_share_by_year"] = dict(zip(uc["year"].to_list(), [round(x, 4) for x in uc["share_unclassified"].to_list()]))
    from qr.guard.trial_ledger import git_state
    rep["git_sha"] = git_state()[0]
    (qa / "gate_report.json").write_text(json.dumps(rep, indent=1, default=str))
    return rep
