"""PIT truncation on REAL data (PRD s9): rebuild bronze -> silver -> gold from files truncated at 3 random cutoffs and require every
value dated <= cutoff to be BIT-identical to the reference build. Any difference means something at t used data after t.

Slow (four silver+gold builds over the full sample, single-threaded for bit-identical floats, D-016). Runs only with
QR_RUN_REALDATA=1 and data/bronze present; the reference is bronze truncated at dev_end (gold never holds later rows while sealed).
"""
import datetime as dt
import os
from pathlib import Path

import numpy as np
import polars as pl
import pytest

from qr.panel.build import build_silver
from qr.signals.gold import build_gold

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


def _build(tmp: Path, cutoff: dt.date) -> dict:
    b = _truncate(tmp / "bronze", cutoff)
    build_silver(raw=ROOT / "data" / "raw", bronze=b, silver=tmp / "silver", qa=tmp / "qa")
    build_gold(tmp / "silver", tmp / "gold")
    px = pl.read_parquet(sorted((tmp / "silver" / "prices").glob("**/*.parquet")))
    return {"prices": px.select("trade_date", "sid", "price_factor", "ret_1d"),
            "universe": pl.read_parquet(sorted((tmp / "silver" / "universe").glob("**/*.parquet"))),
            "signals": pl.read_parquet(tmp / "gold" / "signals" / "signals.parquet"),
            "context": pl.read_parquet(tmp / "gold" / "context" / "context.parquet")}


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


def test_real_data_truncation_bit_identical(tmp_path):
    rng = np.random.default_rng(SEED)
    lo, hi = dt.date(2017, 6, 1).toordinal(), dt.date(2024, 6, 28).toordinal()
    cutoffs = sorted(dt.date.fromordinal(int(x)) for x in rng.integers(lo, hi, 3))
    ref = _build(tmp_path / "ref", DEV_END)
    for c in cutoffs:
        tr = _build(tmp_path / f"cut_{c}", c)
        upto = lambda df, col="trade_date": df.filter(pl.col(col) <= c)
        _same(upto(ref["prices"]), upto(tr["prices"]), ["trade_date", "sid"], f"prices@{c}")
        _same(upto(ref["universe"], "month_start"), upto(tr["universe"], "month_start"), ["month_start", "sid"], f"universe@{c}")
        _same(upto(ref["signals"]), upto(tr["signals"]), ["trade_date", "sid", "signal"], f"signals@{c}")
        _same(upto(ref["context"]), upto(tr["context"]), ["trade_date", "sid"], f"context@{c}")
