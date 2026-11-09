"""OOS lock (PRD section 9, non-negotiable 2).

A commitment device, not a cryptographic guarantee: its credibility comes from git history.
While the state is `sealed`, `clip()` drops every row dated after `dev_end`, and every row whose
forward-return label ends after `dev_end`. The OOS window is opened exactly once by `qr oos --confirm`.

States: sealed -> opened -> read   (a bug-fix re-run after the read uses `reread`, reported side by side).
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import TypeVar

import polars as pl

ROOT = Path(__file__).resolve().parents[3]
LOCK_PATH = ROOT / "oos.lock"
DEV_END = "2024-10-31"
OOS_START = "2024-11-01"
OOS_END = "2026-10-30"

T = TypeVar("T", pl.DataFrame, pl.LazyFrame)


class OOSLockError(RuntimeError):
    pass


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def seal(path: Path = LOCK_PATH, prereg_commit: str | None = None) -> dict:
    """Create the sealed lock. Refuses to overwrite an existing lock."""
    path = Path(path)
    if path.exists():
        raise OOSLockError(f"{path} already exists; the lock is never re-created")
    lock = {"state": "sealed", "dev_end": DEV_END, "oos_start": OOS_START, "oos_end": OOS_END,
            "created_at": _now(), "prereg_commit": prereg_commit, "opened_at": None,
            "opened_commit": None, "headline": None, "results_sha256": None}
    path.write_text(json.dumps(lock, indent=1) + "\n")
    return lock


def read(path: Path = LOCK_PATH) -> dict:
    path = Path(path)
    if not path.exists():
        # A missing lock must never silently open the OOS window.
        raise OOSLockError(f"{path} missing: refusing to load data without the lock")
    return json.loads(path.read_text())


def state(path: Path = LOCK_PATH) -> str:
    return read(path)["state"]


def _write(lock: dict, path: Path) -> None:
    Path(path).write_text(json.dumps(lock, indent=1) + "\n")


def set_headline(model: str, portfolio: dict | str, path: Path = LOCK_PATH) -> dict:
    """Name the frozen headline model/config in the lock. Only allowed while sealed."""
    lock = read(path)
    if lock["state"] != "sealed":
        raise OOSLockError("headline can only be set while sealed")
    lock["headline"] = {"model": model, "portfolio": portfolio}
    _write(lock, path)
    return lock


def set_prereg_commit(sha: str, path: Path = LOCK_PATH) -> dict:
    lock = read(path)
    if lock["state"] != "sealed" or lock["prereg_commit"] is not None:
        raise OOSLockError("prereg_commit can be set once, while sealed")
    lock["prereg_commit"] = sha
    _write(lock, path)
    return lock


def assert_can_open(path: Path = LOCK_PATH) -> dict:
    """Preconditions checked by `qr oos --confirm` (git cleanliness/tag are checked by the CLI)."""
    lock = read(path)
    if lock["state"] != "sealed":
        raise OOSLockError(f"OOS already {lock['state']}: it is read exactly once")
    if not lock["headline"]:
        raise OOSLockError("headline model is not named in the lock")
    return lock


def mark_opened(commit: str, path: Path = LOCK_PATH) -> dict:
    lock = assert_can_open(path)
    lock.update(state="opened", opened_at=_now(), opened_commit=commit)
    _write(lock, path)
    return lock


def mark_read(results_sha256: str, path: Path = LOCK_PATH) -> dict:
    lock = read(path)
    if lock["state"] != "opened":
        raise OOSLockError("can only mark read from state opened")
    lock.update(state="read", results_sha256=results_sha256)
    _write(lock, path)
    return lock


def _date_expr(col: str, schema_dtype) -> pl.Expr:
    c = pl.col(col)
    return c.str.to_date() if schema_dtype == pl.String else c


def clip(df: T, date_col: str = "trade_date", label_end_col: str | None = None,
         path: Path = LOCK_PATH) -> T:
    """Drop rows after `dev_end` while sealed. Every loader in gold and below must call this.

    `label_end_col`: also drop rows whose forward-return label ends after dev_end.
    While state is opened/read the frame is returned unchanged (the one OOS run, or post-read work).
    """
    lock = read(path)
    if lock["state"] != "sealed":
        return df
    dev_end = dt.date.fromisoformat(lock["dev_end"])
    schema = df.collect_schema() if isinstance(df, pl.LazyFrame) else df.schema
    cond = _date_expr(date_col, schema[date_col]) <= dev_end
    if label_end_col is not None:
        cond = cond & (_date_expr(label_end_col, schema[label_end_col]) <= dev_end)
    return df.filter(cond)
