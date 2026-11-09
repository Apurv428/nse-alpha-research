"""raw -> bronze. Idempotent per year; writes data/bronze/<table>/year=YYYY.parquet and _manifest.json."""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import polars as pl

from qr.guard.trial_ledger import git_state
from qr.ingest import parse_cm, parse_fo, parse_mto

# table -> (raw dataset dir, parser)
SOURCES = {
    "cm_daily": [("cm_legacy", parse_cm.parse_legacy), ("cm_udiff", parse_cm.parse_udiff)],
    "fo_daily": [("fo_legacy", parse_fo.parse_legacy), ("fo_udiff", parse_fo.parse_udiff)],
    "mto_daily": [("mto", parse_mto.parse_mto)],
    "index_daily": [("indices", parse_mto.parse_index)],
}


def _date(p: Path) -> dt.date:
    return dt.date.fromisoformat(p.name.split(".")[0])


def build(table: str, raw: Path = Path("data/raw"), out: Path = Path("data/bronze")) -> dict:
    raw, out = Path(raw), Path(out) / table
    out.mkdir(parents=True, exist_ok=True)
    frames: dict[int, list[pl.DataFrame]] = defaultdict(list)
    inputs: dict[str, str] = {}
    for ds, parser in SOURCES[table]:
        for p in sorted((raw / ds).glob("*")):
            d = _date(p)
            frames[d.year].append(parser(p, d))
            inputs[f"{ds}/{p.name}"] = hashlib.sha256(p.read_bytes()).hexdigest()[:16]
    rows = {}
    for y, fs in sorted(frames.items()):
        df = pl.concat(fs, how="vertical_relaxed")
        df.write_parquet(out / f"year={y}.parquet", compression="zstd")
        rows[y] = df.height
    sha, dirty = git_state()
    man = {"table": table, "git_sha": sha, "dirty": dirty, "built_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           "n_input_files": len(inputs), "inputs_hash": hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest(),
           "rows_per_year": rows}
    (out / "_manifest.json").write_text(json.dumps(man, indent=1))
    return man
