"""Gate: legacy and UDiFF CM files agree on close and volume for >= 99.9% of EQ rows, 2024-01-02..2024-07-05.

Needs the raw cache (data/raw). It FAILS when the cache is missing; set QR_ALLOW_NO_DATA=1 (CI does) to skip.
"""
import datetime as dt
import os
from pathlib import Path

import polars as pl
import pytest

from qr.ingest import parse_cm

RAW = Path(__file__).resolve().parents[1] / "data" / "raw"
START, END = dt.date(2024, 1, 2), dt.date(2024, 7, 5)


def _pairs():
    a = {p.name.split(".")[0]: p for p in (RAW / "cm_legacy").glob("2024-*.csv.zip")}
    b = {p.name.split(".")[0]: p for p in (RAW / "cm_udiff").glob("2024-*.csv.zip")}
    ds = sorted(d for d in a if d in b and START <= dt.date.fromisoformat(d) <= END)
    return [(dt.date.fromisoformat(d), a[d], b[d]) for d in ds]


def test_legacy_udiff_agree_on_overlap():
    pairs = _pairs()
    if not pairs:
        if os.environ.get("QR_ALLOW_NO_DATA") == "1":
            pytest.skip("raw cache absent (QR_ALLOW_NO_DATA=1)")
        pytest.fail("overlap files missing: run `qr ingest` for 2024-01-02..2024-07-05")
    tot = agree = 0
    for d, pa, pb in pairs:
        la = parse_cm.parse_legacy(pa, d).filter(pl.col("series") == "EQ")
        ub = parse_cm.parse_udiff(pb, d).filter(pl.col("series") == "EQ")
        j = la.join(ub, on=["trade_date", "isin", "series"], suffix="_u")
        tot += la.height
        agree += j.filter(((pl.col("close") - pl.col("close_u")).abs() < 1e-6) & (pl.col("volume_sh") == pl.col("volume_sh_u"))).height
    assert tot > 0 and agree / tot >= 0.999, f"agreement {agree}/{tot} = {agree / tot:.5f}"
    # the window should be (almost) complete before the gate means anything
    assert len(pairs) >= 100, f"only {len(pairs)} overlapping sessions downloaded"


def test_parsers_reject_wrong_filename_date(tmp_path):
    import io, zipfile

    csv = "SYMBOL,SERIES,OPEN,HIGH,LOW,CLOSE,LAST,PREVCLOSE,TOTTRDQTY,TOTTRDVAL,TIMESTAMP,TOTALTRADES,ISIN,\nAAA,EQ,1,1,1,1,1,1,10,10,02-JAN-2012,1,INE0,\n"
    z = tmp_path / "x.csv.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("x.csv", csv)
    with pytest.raises(ValueError):
        parse_cm.parse_legacy(z, dt.date(2012, 1, 3))
    assert parse_cm.parse_legacy(z, dt.date(2012, 1, 2)).height == 1


def test_legacy_two_digit_year_timestamp(tmp_path):
    import datetime as dt
    import io
    import zipfile

    from qr.ingest.parse_cm import parse_legacy
    csv = ("SYMBOL,SERIES,OPEN,HIGH,LOW,CLOSE,LAST,PREVCLOSE,TOTTRDQTY,TOTTRDVAL,TIMESTAMP,TOTALTRADES,ISIN\n"
           "AAA,EQ,1,1,1,1,1,1,10,10,13-Jul-20,1,INE000A01010\n")
    p = tmp_path / "2020-07-13.csv.zip"
    with zipfile.ZipFile(p, "w") as z:
        z.writestr("cm13JUL2020bhav.csv", csv)
    assert parse_legacy(p, dt.date(2020, 7, 13)).height == 1
    with pytest.raises(ValueError):
        parse_legacy(p, dt.date(2020, 7, 14))
