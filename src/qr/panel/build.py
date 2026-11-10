"""bronze -> silver orchestration with stage manifests and data-QA outputs (runs/data_qa/).

Data QA may touch OOS rows for row counts and the jump audit only; it computes no return statistics
on them (PRD section 9.2).
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path

import polars as pl
import yaml

from qr.guard.trial_ledger import git_state
from qr.ingest.corpactions import build_corp_actions
from qr.panel.adjust import build_prices, map_events_to_sid
from qr.panel.bench import SECTOR_FILES, build_bench, build_sectors
from qr.panel.futures import build_fut_cont
from qr.panel.master import build_security_master, session_calendar
from qr.panel.universe import build_universe

ROOT = Path(__file__).resolve().parents[3]
CFG = yaml.safe_load((ROOT / "config" / "research.yaml").read_text())


def _counts(s) -> dict:
    """Label -> count. One value_counts call (its row order is not stable across calls)."""
    vc = s.value_counts(sort=True)
    return dict(zip(vc[s.name].to_list(), vc["count"].to_list()))


def _read(table: str, bronze: Path) -> pl.DataFrame:
    files = sorted((bronze / table).glob("year=*.parquet"))
    # file_sha (64-char hex per row) is bronze provenance only; dropping it here keeps the full 2012-2026 build inside ~7 GB RAM
    rd = lambda f: (lambda d: d.drop([c for c in ("file_sha",) if c in d.columns]))(pl.read_parquet(f))
    return pl.concat([rd(f) for f in files], how="vertical_relaxed") if files else pl.DataFrame()


def _write_stage(df: pl.DataFrame, out: Path, name: str, inputs: dict, partition_year: str | None = None) -> None:
    d = out / name
    d.mkdir(parents=True, exist_ok=True)
    rows = {}
    if partition_year:
        yrs = df.with_columns(pl.col(partition_year).dt.year().alias("_y"))
        for (y,), g in yrs.group_by("_y"):
            g.drop("_y").write_parquet(d / f"year={y}.parquet", compression="zstd")
            rows[int(y)] = g.height
    else:
        df.write_parquet(d / f"{name}.parquet", compression="zstd")
        rows["all"] = df.height
    sha, dirty = git_state()
    cfg_hash = hashlib.sha256((ROOT / "config" / "research.yaml").read_bytes()).hexdigest()[:16]
    (d / "_manifest.json").write_text(json.dumps({
        "table": name, "git_sha": sha, "dirty": dirty, "config_hash": cfg_hash, "inputs": inputs,
        "rows": rows, "built_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}, indent=1, default=str))


def build_silver(raw: Path = Path("data/raw"), bronze: Path = Path("data/bronze"), silver: Path = Path("data/silver"),
                 qa: Path = Path("runs/data_qa")) -> dict:
    raw, bronze, silver, qa = Path(raw), Path(bronze), Path(silver), Path(qa)
    qa.mkdir(parents=True, exist_ok=True)
    cm, mto, fo, idx = (_read(t, bronze) for t in ("cm_daily", "mto_daily", "fo_daily", "index_daily"))
    ca_dir = raw / "corpactions"
    ca = build_corp_actions(ca_dir) if list(ca_dir.glob("*.csv")) else None
    cal = session_calendar(cm)
    master, pair_map = build_security_master(cm, cal, ca)
    events, n_unmapped = (map_events_to_sid(ca, master) if ca is not None else (None, 0))
    prices, audit, stats = build_prices(cm, mto, pair_map, cal, events, fno_days=fo if fo.height else None)
    uni = build_universe(prices, cal, fo if fo.height else None, master, CFG)
    fut = build_fut_cont(fo, cal, master, prices) if fo.height else pl.DataFrame()
    bench = build_bench(idx, raw / "manual" / "n500_tri.csv")
    snaps = {r["date"]: r.get("snapshot") for r in map(json.loads, (raw / "_manifest.jsonl").read_text().splitlines())
             if r["dataset"] == "static"} if (raw / "_manifest.jsonl").exists() else {}
    sectors = build_sectors(master, raw / "static", snaps)
    inputs = {"bronze_manifests": {t: json.loads((bronze / t / "_manifest.json").read_text())["inputs_hash"]
                                   for t in ("cm_daily", "mto_daily", "fo_daily", "index_daily") if (bronze / t / "_manifest.json").exists()},
              "corp_actions_files": sorted(p.name for p in ca_dir.glob("*.csv"))}
    _write_stage(master, silver, "security_master", inputs)
    _write_stage(prices, silver, "prices", inputs, partition_year="trade_date")
    _write_stage(uni, silver, "universe", inputs)
    if fut.height:
        _write_stage(fut, silver, "fut_cont", inputs)
    _write_stage(bench, silver, "bench", inputs)
    _write_stage(sectors, silver, "sectors", inputs)
    _write_stage(cal, silver, "calendar", inputs)
    # ---- data QA (counts and audit only; no return statistics) ----
    audit.write_csv(qa / "jump_audit.csv")
    master.write_csv(qa / "security_links.csv")
    cal.with_columns(pl.col("trade_date").dt.year().alias("year")).group_by("year").agg(n_sessions=pl.len()).sort("year") \
        .write_csv(qa / "sessions_per_year.csv")
    rows = (cm.group_by("trade_date").agg(cm_rows=pl.len()).join(mto.group_by("trade_date").agg(mto_rows=pl.len()), on="trade_date", how="full", coalesce=True)
            .join(fo.group_by("trade_date").agg(fo_rows=pl.len()), on="trade_date", how="full", coalesce=True).sort("trade_date"))
    rows.write_csv(qa / "rows_per_day.csv")
    summary = {"stats": stats, "n_sessions": cal.height, "n_sids": master["sid"].n_unique(),
               "n_pairs": master.height, "ca_rows": 0 if ca is None else ca.height, "ca_unmapped": n_unmapped,
               "ca_actions": {} if ca is None else _counts(ca["action"]),
               "jump_audit_by_resolution": _counts(audit["resolution"]) if audit.height else {},
               "link_reasons": _counts(master["link_reason"])}
    (qa / "silver_summary.json").write_text(json.dumps(summary, indent=1, default=str))
    return summary
