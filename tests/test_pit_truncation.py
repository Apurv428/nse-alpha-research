"""PIT truncation on REAL data (PRD s9): rebuild bronze -> silver -> gold from files truncated at 3 random cutoffs and require every
value dated <= cutoff to be BIT-identical to the reference build. Any difference means something at t used data after t.

Slow (four silver+gold builds over the full sample, single-threaded for bit-identical floats, D-016). Runs only with
QR_RUN_REALDATA=1 and data/bronze present; the reference is bronze truncated at dev_end (gold never holds later rows while sealed).
"""
import datetime as dt
import os
from pathlib import Path

import shutil
import subprocess
import sys

import numpy as np
import polars as pl
import pytest


ROOT = Path(__file__).resolve().parents[1]
BRONZE = ROOT / "data" / "bronze"
TABLES = ("cm_daily", "mto_daily", "fo_daily", "index_daily")
DEV_END = dt.date(2024, 10, 31)
SEED = 20261110

pytestmark = pytest.mark.skipif(os.environ.get("QR_RUN_REALDATA") != "1" or not (BRONZE / "cm_daily").exists(),
                                reason="real-data test: set QR_RUN_REALDATA=1 after building data/bronze")


def _truncate(dst: Path, cutoff: dt.date) -> Path:
    for t in TABLES:
        (dst / t).mkdir(parents=True, exist_ok=True)
        for f in sorted((BRONZE / t).glob("year=*.parquet")):
            df = pl.read_parquet(f).filter(pl.col("trade_date") <= cutoff)
            if df.height:
                df.write_parquet(dst / t / f.name)
    return dst


def _build(tmp: Path, cutoff: dt.date, sectors_from: Path | None = None) -> Path:
    """Build silver+gold from bronze truncated at `cutoff` in a SUBPROCESS (frees memory between builds on a 7 GB box, D-031)."""
    b = _truncate(tmp / "bronze", cutoff)
    code = ("from pathlib import Path; from qr.panel.build import build_silver; from qr.signals.gold import build_gold; "
            f"t = Path({str(tmp)!r}); build_silver(raw=Path({str(ROOT / 'data' / 'raw')!r}), bronze=t / 'bronze', silver=t / 'silver', qa=t / 'qa', "
            f"sectors_from={None if sectors_from is None else str(sectors_from)!r} and Path({str(sectors_from)!r})); "
            "build_gold(t / 'silver', t / 'gold')")
    env = {**os.environ, "POLARS_MAX_THREADS": "1", "MALLOC_ARENA_MAX": "2"}
    subprocess.run([sys.executable, "-c", code], check=True, env=env, cwd=ROOT)
    shutil.rmtree(b)
    return tmp


def _load(root: Path, what: str, c: dt.date, y: int) -> pl.DataFrame:
    """Rows of one calendar year that are dated <= c (lazy scan: one year in memory at a time)."""
    col, files = {"prices": ("trade_date", root / "silver" / "prices" / "*.parquet"),
                  "universe": ("month_start", root / "silver" / "universe" / "*.parquet"),
                  "signals": ("trade_date", root / "gold" / "signals" / "signals.parquet"),
                  "context": ("trade_date", root / "gold" / "context" / "context.parquet")}[what]
    lf = pl.scan_parquet(str(files)).filter((pl.col(col) <= c) & (pl.col(col).dt.year() == y))
    if what == "prices":
        lf = lf.select("trade_date", "sid", "price_factor", "ret_1d")
    return lf.collect()


def _same(a: pl.DataFrame, b: pl.DataFrame, keys: list[str], what: str):
    a, b = a.sort(keys), b.sort(keys)
    assert a.height == b.height, f"{what}: {a.height} rows in reference vs {b.height} truncated"
    for c in a.columns:
        x, y = a[c], b[c]
        if x.dtype in (pl.Float64, pl.Float32):
            xa, ya = x.to_numpy(), y.to_numpy()
            same = (xa == ya) | (np.isnan(xa) & np.isnan(ya))
            assert same.all(), f"{what}.{c}: {int((~same).sum())} values differ, first at row {int(np.argmin(same))}"
        else:
            assert x.equals(y, check_names=False), f"{what}.{c} differs"


KEYS = {"prices": ["trade_date", "sid"], "universe": ["month_start", "sid"], "signals": ["trade_date", "sid", "signal"],
        "context": ["trade_date", "sid"]}


def test_real_data_truncation_bit_identical(tmp_path):
    rng = np.random.default_rng(SEED)
    lo, hi = dt.date(2017, 6, 1).toordinal(), dt.date(2024, 6, 28).toordinal()
    cutoffs = sorted(dt.date.fromordinal(int(x)) for x in rng.integers(lo, hi, 3))
    ref = _build(tmp_path / "ref", DEV_END)
    for c in cutoffs:
        # sector labels are a non-PIT 2026 snapshot by design (PRD s4): hold the reference's mapped table fixed, so everything else
        # (prices, universe, raw/z/z_neu signals, beta, size) must still be bit-identical (D-032)
        tr = _build(tmp_path / f"cut_{c}", c, sectors_from=ref / "silver" / "sectors" / "sectors.parquet")
        for what, keys in KEYS.items():
            for y in range(2012, c.year + 1):
                _same(_load(ref, what, c, y), _load(tr, what, c, y), keys, f"{what}@{c} year {y}")
        shutil.rmtree(tr)
