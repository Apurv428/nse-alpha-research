"""The ONLY way research code reads silver/gold tables. Every loader passes through `guard.oos_lock.clip()`, so
development code never sees a date after dev_end while the lock is sealed (PRD section 2). A lint test
(tests/test_no_raw_reads.py) fails on any read_parquet/scan_parquet outside the allowed data-layer modules."""
from __future__ import annotations

from pathlib import Path

import polars as pl

from qr.guard.oos_lock import clip

SILVER, GOLD = Path("data/silver"), Path("data/gold")


def _scan(d: Path, name: str, partitioned: bool) -> pl.LazyFrame:
    return pl.scan_parquet(d / name / ("year=*.parquet" if partitioned else f"{name}.parquet"))


def load_prices(silver: Path = SILVER) -> pl.DataFrame:
    return clip(_scan(silver, "prices", True)).collect()


def load_calendar(silver: Path = SILVER) -> pl.DataFrame:
    return clip(_scan(silver, "calendar", False)).collect()


def load_bench(silver: Path = SILVER) -> pl.DataFrame:
    return clip(_scan(silver, "bench", False)).collect()


def load_universe(silver: Path = SILVER) -> pl.DataFrame:
    return clip(_scan(silver, "universe", False), date_col="month_start").collect()


def load_sectors(silver: Path = SILVER) -> pl.DataFrame:  # a static snapshot, no dates
    return _scan(silver, "sectors", False).collect()


def load_fut_cont(silver: Path = SILVER) -> pl.DataFrame:
    return clip(_scan(silver, "fut_cont", False)).collect()


def load_gold(name: str, gold: Path = GOLD) -> pl.DataFrame:
    lf = pl.scan_parquet(gold / name / f"{name}.parquet")
    cols = lf.collect_schema().names()
    return clip(lf, label_end_col="label_end_date" if "label_end_date" in cols else None).collect()
