"""MTO delivery file and all-index-close parsers -> bronze.mto_daily, bronze.index_daily."""
from __future__ import annotations

import datetime as dt
import io
from pathlib import Path

import polars as pl


def parse_mto(path: Path, trade_date: dt.date) -> pl.DataFrame:
    """Record type 20 rows only: 20,srno,symbol,series,qty_traded,deliv_qty,deliv_pct. Header lines skipped."""
    rows, bad = [], 0
    text = Path(path).read_text(errors="replace")
    stamp = None
    for line in text.splitlines():
        if line.startswith("Trade Date <"):
            stamp = dt.datetime.strptime(line.split("<")[1].split(">")[0], "%d-%b-%Y").date()
        if not line.startswith("20,"):
            continue
        f = [x.strip() for x in line.split(",")]
        if len(f) != 7:
            bad += 1
            continue
        rows.append((f[2], f[3], f[4], f[5], f[6]))
    if stamp is not None and stamp != trade_date:
        raise ValueError(f"{path}: in-file date {stamp} != filename date {trade_date}")
    df = pl.DataFrame(rows, schema=["symbol", "series", "qty_traded", "deliv_qty", "deliv_pct"], orient="row")
    return df.select(pl.lit(trade_date).alias("trade_date"), "symbol", "series",
                     pl.col("qty_traded").cast(pl.Int64, strict=False),
                     pl.col("deliv_qty").cast(pl.Int64, strict=False),
                     pl.col("deliv_pct").cast(pl.Float64, strict=False)).filter(
        pl.col("series").is_in(["EQ", "BE", "BZ"]))


def parse_index(path: Path, trade_date: dt.date) -> pl.DataFrame:
    df = pl.read_csv(Path(path), infer_schema_length=0, truncate_ragged_lines=True)
    df = df.rename({c: c.strip() for c in df.columns})
    d = df["Index Date"].str.to_date("%d-%m-%Y").unique().to_list()
    if d and d != [trade_date]:
        raise ValueError(f"{path}: in-file dates {d} != filename date {trade_date}")
    num = lambda c: pl.col(c).str.strip_chars().cast(pl.Float64, strict=False)  # "-" -> null
    return df.select(pl.lit(trade_date).alias("trade_date"), pl.col("Index Name").str.strip_chars().alias("index_name"),
                     num("Closing Index Value").alias("close"), num("P/E").alias("pe"), num("P/B").alias("pb"),
                     num("Div Yield").alias("div_yield_pct"))
