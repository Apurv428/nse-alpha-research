"""CM bhavcopy parsers (legacy and UDiFF) -> one bronze schema (PRD section 4, bronze.cm_daily)."""
from __future__ import annotations

import datetime as dt
import hashlib
import io
import zipfile
from pathlib import Path

import polars as pl

KEEP_SERIES = ["EQ", "BE", "BZ"]
SCHEMA = {"trade_date": pl.Date, "isin": pl.String, "series": pl.String, "symbol": pl.String,
          "open": pl.Float64, "high": pl.Float64, "low": pl.Float64, "close": pl.Float64, "last": pl.Float64,
          "prev_close": pl.Float64, "volume_sh": pl.Int64, "value_inr": pl.Float64, "n_trades": pl.Int64,
          "src": pl.String, "file_sha": pl.String}


def _read_zip_csv(path: Path) -> tuple[bytes, str]:
    raw = Path(path).read_bytes()
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        name = z.namelist()[0]
        return z.read(name), hashlib.sha256(raw).hexdigest()


def parse_legacy(path: Path, trade_date: dt.date) -> pl.DataFrame:
    data, sha = _read_zip_csv(path)
    df = pl.read_csv(io.BytesIO(data), infer_schema_length=0, truncate_ragged_lines=True)
    df = df.rename({c: c.strip() for c in df.columns}).filter(pl.col("SERIES").str.strip_chars().is_in(KEEP_SERIES))
    file_dates = df["TIMESTAMP"].str.to_date("%d-%b-%Y").unique().to_list()
    if file_dates and file_dates != [trade_date]:
        raise ValueError(f"{path}: in-file dates {file_dates} != filename date {trade_date}")
    out = df.select(
        pl.lit(trade_date).alias("trade_date"),
        pl.col("ISIN").str.strip_chars().alias("isin"),
        pl.col("SERIES").str.strip_chars().alias("series"),
        pl.col("SYMBOL").str.strip_chars().alias("symbol"),
        pl.col("OPEN").cast(pl.Float64).alias("open"), pl.col("HIGH").cast(pl.Float64).alias("high"),
        pl.col("LOW").cast(pl.Float64).alias("low"), pl.col("CLOSE").cast(pl.Float64).alias("close"),
        pl.col("LAST").cast(pl.Float64).alias("last"), pl.col("PREVCLOSE").cast(pl.Float64).alias("prev_close"),
        pl.col("TOTTRDQTY").cast(pl.Int64).alias("volume_sh"), pl.col("TOTTRDVAL").cast(pl.Float64).alias("value_inr"),
        pl.col("TOTALTRADES").cast(pl.Int64).alias("n_trades"),
        pl.lit("legacy").alias("src"), pl.lit(sha).alias("file_sha"))
    return out


def parse_udiff(path: Path, trade_date: dt.date) -> pl.DataFrame:
    data, sha = _read_zip_csv(path)
    df = pl.read_csv(io.BytesIO(data), infer_schema_length=0, truncate_ragged_lines=True)
    df = df.rename({c: c.strip() for c in df.columns}).filter(pl.col("SctySrs").str.strip_chars().is_in(KEEP_SERIES))
    file_dates = df["TradDt"].str.to_date("%Y-%m-%d").unique().to_list()
    if file_dates and file_dates != [trade_date]:
        raise ValueError(f"{path}: in-file dates {file_dates} != filename date {trade_date}")
    return df.select(
        pl.lit(trade_date).alias("trade_date"),
        pl.col("ISIN").str.strip_chars().alias("isin"),
        pl.col("SctySrs").str.strip_chars().alias("series"),
        pl.col("TckrSymb").str.strip_chars().alias("symbol"),
        pl.col("OpnPric").cast(pl.Float64).alias("open"), pl.col("HghPric").cast(pl.Float64).alias("high"),
        pl.col("LwPric").cast(pl.Float64).alias("low"), pl.col("ClsPric").cast(pl.Float64).alias("close"),
        pl.col("LastPric").cast(pl.Float64).alias("last"), pl.col("PrvsClsgPric").cast(pl.Float64).alias("prev_close"),
        pl.col("TtlTradgVol").cast(pl.Int64).alias("volume_sh"), pl.col("TtlTrfVal").cast(pl.Float64).alias("value_inr"),
        pl.col("TtlNbOfTxsExctd").cast(pl.Int64).alias("n_trades"),
        pl.lit("udiff").alias("src"), pl.lit(sha).alias("file_sha"))
