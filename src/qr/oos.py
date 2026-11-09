"""`qr oos`: the one-time read of the locked OOS window, plus a mechanics rehearsal that never touches the lock.

run_oos(): preconditions (clean tree, HEAD tagged `oos-candidate`, state sealed, headline named, frozen files match the lock hash)
-> mark_opened + commit the lock -> rebuild gold on the full sample into data/gold_oos -> score with the FROZEN model -> P0/P1/P2
gross and net, capacity, PSR(0) and bootstrap CIs -> runs/oos/ -> results hash -> mark_read + commit the lock.
rehearse(): same code path on the last 52 weeks of the DEVELOPMENT window while sealed. In-sample for the frozen model, so it checks
mechanics only; its numbers are never reported.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np
import polars as pl

from qr.eval import ic as I
from qr.guard import oos_lock
from qr.models import freeze as F
from qr.models.run import wide_features
from qr.panel import io
from qr.portfolio.backtest import attach_universe, build_panel
from qr.portfolio.run import evaluate_books, scores_from_df
from qr.stats.newey_west import nw_tstat

ROOT = Path(__file__).resolve().parents[2]


def _git(*a: str, cwd: Path = ROOT) -> str:
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, check=True).stdout.strip()


def check_preconditions(lock_path: Path = oos_lock.LOCK_PATH, frozen_dir: Path = F.FROZEN_DIR, repo: Path = ROOT) -> dict:
    lock = oos_lock.assert_can_open(lock_path)                                   # sealed, headline named
    if _git("status", "--porcelain", cwd=repo):
        raise oos_lock.OOSLockError("working tree is not clean")
    if "oos-candidate" not in _git("tag", "--points-at", "HEAD", cwd=repo).split():
        raise oos_lock.OOSLockError("HEAD is not tagged oos-candidate")
    sha = hashlib.sha256((Path(frozen_dir) / "frozen.json").read_bytes()).hexdigest()
    if sha != lock["headline"]["portfolio"].get("frozen_sha256"):
        raise oos_lock.OOSLockError("frozen.json does not match the hash recorded in the lock")
    return lock


def evaluate_window(frozen: dict, gold: Path, silver: Path, start: dt.date, end: dt.date, out: Path, tag: str) -> dict:
    sig, ctx, fwd = io.load_gold("signals", gold), io.load_gold("context", gold), io.load_gold("fwd_returns", gold)
    cal, bench = io.load_calendar(silver), io.load_bench(silver)
    X, _ = wide_features(sig, ctx)
    X = X.filter((pl.col("trade_date") >= start) & (pl.col("trade_date") <= end))
    sc = F.score(frozen, X)
    model = frozen["model"]
    # rank IC of the frozen score on the window (h = 5), Newey-West t
    ics = I.ic_series(sc.select("trade_date", "sid", pl.lit(model).alias("signal"), "score"), fwd, "score").filter(pl.col("h") == 5).sort("trade_date")
    x = ics["rank_ic"].drop_nulls().to_numpy()
    nw = nw_tstat(x, 5) if len(x) > 10 else {"mean": float("nan"), "t_nw": float("nan")}
    universe, fut = io.load_universe(silver), io.load_fut_cont(silver)
    panel = build_panel(io.load_prices(silver), cal, bench, universe, fut)
    scores = scores_from_df(sc, panel)
    attach_universe(panel, universe, list(scores))
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    m = evaluate_books(panel, scores, fwd.filter(pl.col("h") == 5), cal, bench, out, model, tag, start, end, sensitivities=True, log=False)
    m[f"score.{tag}.mean_rank_ic_h5"], m[f"score.{tag}.t_nw_h5"] = nw["mean"], nw["t_nw"]
    (out / "metrics.json").write_text(json.dumps(m, indent=1, default=str))
    return m


def rehearse(gold: Path = Path("data/gold"), silver: Path = Path("data/silver"), out_root: Path = Path("runs")) -> dict:
    """Mechanics check on the last 52 weeks of the development window (sealed lock, nothing after dev_end is loaded)."""
    if oos_lock.state() != "sealed":
        raise oos_lock.OOSLockError("rehearsal runs only while sealed")
    frozen = F.load_frozen()
    end = dt.date.fromisoformat(oos_lock.read()["dev_end"])
    start = end - dt.timedelta(weeks=52)
    out = Path(out_root) / "oos_rehearsal"
    m = evaluate_window(frozen, gold, silver, start, end, out, "rehearsal")
    (out / "README.txt").write_text("MECHANICS ONLY. In-sample for the frozen model. These numbers are never reported.\n")
    return m


def run_oos(confirm: bool, silver: Path = Path("data/silver"), out_root: Path = Path("runs")) -> dict:
    if not confirm:
        raise oos_lock.OOSLockError("pass --confirm; this reads the locked OOS window exactly once")
    lock = check_preconditions()
    frozen = F.load_frozen()
    commit = _git("rev-parse", "HEAD")
    oos_lock.mark_opened(commit)
    _git("add", "oos.lock"); _git("commit", "-m", "Open OOS lock (state: opened)")
    out = Path(out_root) / "oos"
    from qr.signals.gold import build_gold
    gold_oos = Path("data/gold_oos")
    build_gold(silver, gold_oos)                                              # unclipped now: the whole pipeline once
    m = evaluate_window(frozen, gold_oos, silver, dt.date.fromisoformat(lock["oos_start"]), dt.date.fromisoformat(lock["oos_end"]), out, "oos")
    sha = hashlib.sha256((out / "metrics.json").read_bytes()).hexdigest()
    oos_lock.mark_read(sha)
    _git("add", "oos.lock"); _git("commit", "-m", "Mark OOS read (state: read)")
    return m
