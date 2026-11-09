"""Append-only trial ledger (PRD section 9.3, non-negotiable 3).

`@trial(kind)` wraps `qr eval|fit|backtest` entry points. The wrapped function must return a dict with
`params`, `window`, `freq` and a weekly return series `returns` (polars DataFrame with columns
[date, ret]); optional `rank_ic`, `t_nw`. The decorator writes the returns file and APPENDS one JSON
line to trials/trials.jsonl *before* handing the result back to the caller (who prints it).
Only a crashed run goes unlogged. A run later found buggy is kept; supersession is a separate appended
event, so the file is never rewritten (DECISIONS D-007).
"""
from __future__ import annotations

import datetime as dt
import functools
import hashlib
import json
import os
import subprocess
import uuid
from pathlib import Path

import numpy as np
import polars as pl
from scipy import stats

ROOT = Path(__file__).resolve().parents[3]
LEDGER = ROOT / "trials" / "trials.jsonl"
RUNS = ROOT / "runs"


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    except Exception:
        return "unknown"


def git_state() -> tuple[str, bool]:
    sha = _git("rev-parse", "HEAD")
    dirty = bool(_git("status", "--porcelain")) if sha != "unknown" else True
    return sha, dirty


def config_hash(params: dict) -> str:
    cfg = (ROOT / "config" / "research.yaml").read_bytes() if (ROOT / "config" / "research.yaml").exists() else b""
    costs = (ROOT / "config" / "costs.yaml").read_bytes() if (ROOT / "config" / "costs.yaml").exists() else b""
    blob = cfg + costs + json.dumps(params, sort_keys=True, default=str).encode()
    return hashlib.sha256(blob).hexdigest()[:16]


def sharpe_moments(ret: np.ndarray) -> dict:
    """Per-period (weekly) Sharpe, skewness and (non-excess) kurtosis for the DSR."""
    r = np.asarray(ret, dtype=float)
    r = r[np.isfinite(r)]
    if len(r) < 3 or r.std(ddof=1) == 0:
        return {"n_obs": int(len(r)), "sr": float("nan"), "skew": float("nan"), "kurt": float("nan")}
    return {"n_obs": int(len(r)), "sr": float(r.mean() / r.std(ddof=1)),
            "skew": float(stats.skew(r)), "kurt": float(stats.kurtosis(r, fisher=False))}


def append_line(rec: dict, ledger: Path = LEDGER) -> None:
    ledger = Path(ledger)
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a") as f:  # append-only
        f.write(json.dumps(rec, sort_keys=False, default=str) + "\n")
        f.flush()
        os.fsync(f.fileno())


def log_trial(kind: str, params: dict, window: tuple[str, str], freq: str, returns: pl.DataFrame,
              rank_ic: float | None = None, t_nw: float | None = None,
              ledger: Path = LEDGER, runs: Path = RUNS) -> dict:
    assert kind in ("signal", "combo", "portfolio")
    trial_id = f"{kind[:3]}-{dt.datetime.now(dt.timezone.utc):%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:6]}"
    out_dir = Path(runs) / trial_id
    out_dir.mkdir(parents=True, exist_ok=True)
    ret_path = out_dir / "weekly_returns.parquet"
    returns.write_parquet(ret_path)
    sha, dirty = git_state()
    m = sharpe_moments(returns["ret"].to_numpy())
    rec = {"trial_id": trial_id, "ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           "git_sha": sha, "dirty": dirty, "config_hash": config_hash(params), "kind": kind,
           "params": params, "window": list(window), "freq": freq, **m,
           "rank_ic": rank_ic, "t_nw": t_nw,
           "returns_path": str(ret_path.relative_to(ROOT)) if str(ret_path).startswith(str(ROOT)) else str(ret_path),
           "superseded_by": None}
    append_line(rec, ledger)
    return rec


def supersede(old_id: str, new_id: str, ledger: Path = LEDGER) -> None:
    append_line({"event": "supersede", "trial_id": old_id, "superseded_by": new_id,
                 "ts": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}, ledger)


def load_trials(ledger: Path = LEDGER) -> list[dict]:
    """All trials (superseded ones included, with `superseded_by` resolved from supersede events)."""
    ledger = Path(ledger)
    if not ledger.exists():
        return []
    trials, sup = {}, {}
    for line in ledger.read_text().splitlines():
        r = json.loads(line)
        if r.get("event") == "supersede":
            sup[r["trial_id"]] = r["superseded_by"]
        else:
            trials[r["trial_id"]] = r
    for k, v in sup.items():
        if k in trials:
            trials[k]["superseded_by"] = v
    return list(trials.values())


def n_all(ledger: Path = LEDGER) -> int:
    """True trial count for the deflated Sharpe: every logged trial, superseded ones included."""
    return len(load_trials(ledger))


def trial(kind: str):
    """Decorator: log the returned run to the ledger BEFORE returning it (so before anything prints)."""
    def deco(fn):
        @functools.wraps(fn)
        def wrapper(*a, **kw):
            res = fn(*a, **kw)
            rec = log_trial(kind, res["params"], tuple(res["window"]), res["freq"], res["returns"],
                            res.get("rank_ic"), res.get("t_nw"))
            res["trial"] = rec
            return res
        return wrapper
    return deco
