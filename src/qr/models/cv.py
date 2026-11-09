"""Purged, embargoed, expanding-window walk-forward folds (PRD section 7).

A training row dated t has label window t+1 .. t+1+h. Purge: drop rows whose label ends on/after test_start
(h + 1 = 6 sessions). Embargo: 21 more sessions. So the last training date is PURGE+EMBARGO = 27 sessions before each
test start. Folds refit once a year; test folds tile 2017-01-02 .. 2024-10-31 with no gaps or overlaps.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import polars as pl

H = 5
PURGE = H + 1
EMBARGO = 21
GAP = PURGE + EMBARGO  # 27 sessions between the last training date and test_start
EVERY = 5  # train on every 5th date only (5-day labels on consecutive days overlap 80%)

TEST_WINDOWS = [("2017-01-02", "2017-12-31")] + [(f"{y}-01-01", f"{y}-12-31") for y in range(2018, 2024)] + [("2024-01-01", "2024-10-31")]


def make_folds(calendar: pl.DataFrame, train_start: str = "2013-02-01", dev_end: str = "2024-10-31") -> pl.DataFrame:
    """calendar: (trade_date, sess) over the development window. Returns gold.folds."""
    cal = calendar.sort("sess")
    d, s = cal["trade_date"].to_list(), cal["sess"].to_list()
    first_train = next(x for x in d if x >= dt.date.fromisoformat(train_start))
    rows = []
    for k, (a, b) in enumerate(TEST_WINDOWS, 1):
        a_, b_ = dt.date.fromisoformat(a), min(dt.date.fromisoformat(b), dt.date.fromisoformat(dev_end))
        t_in = [x for x in d if a_ <= x <= b_]
        test_start, test_end = t_in[0], t_in[-1]
        ts = s[d.index(test_start)]
        last_train_sess = ts - GAP
        train_end = next(x for x, y in zip(d, s) if y == last_train_sess)
        rows.append({"fold_id": k, "train_start": first_train, "train_end": train_end, "test_start": test_start, "test_end": test_end,
                     "purge_days": PURGE, "embargo_days": EMBARGO})
    return pl.DataFrame(rows)


def train_sessions(calendar: pl.DataFrame, fold: dict, every: int = EVERY) -> np.ndarray:
    """Sessions of training rows: every `every`-th session from train_start up to train_end."""
    c = calendar.filter((pl.col("trade_date") >= fold["train_start"]) & (pl.col("trade_date") <= fold["train_end"])).sort("sess")
    return c["sess"].to_numpy()[::every]


def inner_split(train_sess: np.ndarray, val_frac: float = 0.2, gap: int = GAP) -> tuple[np.ndarray, np.ndarray]:
    """Inner purged split: validation = last 20% of the training dates; inner training stops `gap` sessions before the
    first validation date (same purge + embargo)."""
    n_val = max(1, int(round(len(train_sess) * val_frac)))
    val = train_sess[-n_val:]
    inner = train_sess[train_sess <= val[0] - gap]
    return inner, val
