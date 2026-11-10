"""F&O bhavcopy parsers (legacy and UDiFF), stock futures only -> bronze.fo_daily."""
from __future__ import annotations

import datetime as dt
import hashlib
import io
import zipfile
from pathlib import Path

import polars as pl


def _read(path: Path):
    raw = Path(path).read_bytes()
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        return z.read(z.namelist()[0]), hashlib.sha256(raw).hexdigest()


def parse_legacy(path: Path, trade_date: dt.date) -> pl.DataFrame:
    data, sha = _read(path)
    df = pl.read_csv(io.BytesIO(data), infer_schema_length=0, truncate_ragged_lines=True)
    df = df.rename({c: c.strip() for c in df.columns}).filter(pl.col("INSTRUMENT").str.strip_chars() == "FUTSTK")
    fd = df["TIMESTAMP"].str.to_date("%d-%b-%Y").unique().to_list()
    if fd and fd != [trade_date]:
        raise ValueError(f"{path}: in-file dates {fd} != filename date {trade_date}")
    return df.select(
        pl.lit(trade_date).alias("trade_date"), pl.col("SYMBOL").str.strip_chars().alias("symbol"),
        pl.col("EXPIRY_DT").str.to_date("%d-%b-%Y").alias("expiry"),
        pl.col("CLOSE").cast(pl.Float64).alias("close"), pl.col("SETTLE_PR").cast(pl.Float64).alias("settle"),
        pl.col("CONTRACTS").cast(pl.Float64).cast(pl.Int64).alias("contracts"),
        (pl.col("VAL_INLAKH").cast(pl.Float64) * 1e5).alias("value_inr"),
        pl.col("OPEN_INT").cast(pl.Float64).cast(pl.Int64).alias("oi"), pl.lit(None, dtype=pl.Int64).alias("lot_size"),
        pl.lit("legacy").alias("src"), pl.lit(sha).alias("file_sha"))


def parse_udiff(path: Path, trade_date: dt.date) -> pl.DataFrame:
    data, sha = _read(path)
    df = pl.read_csv(io.BytesIO(data), infer_schema_length=0, truncate_ragged_lines=True)
    df = df.rename({c: c.strip() for c in df.columns}).filter(pl.col("FinInstrmTp").str.strip_chars() == "STF")
    fd = df["TradDt"].str.to_date("%Y-%m-%d").unique().to_list()
    if fd and fd != [trade_date]:
        raise ValueError(f"{path}: in-file dates {fd} != filename date {trade_date}")
    return df.select(
        pl.lit(trade_date).alias("trade_date"), pl.col("TckrSymb").str.strip_chars().alias("symbol"),
        pl.col("XpryDt").str.to_date("%Y-%m-%d").alias("expiry"),
        pl.col("ClsPric").cast(pl.Float64).alias("close"), pl.col("SttlmPric").cast(pl.Float64).alias("settle"),
        pl.col("TtlTradgVol").cast(pl.Float64).cast(pl.Int64).alias("contracts"),
        pl.col("TtlTrfVal").cast(pl.Float64).alias("value_inr"),
        pl.col("OpnIntrst").cast(pl.Float64).cast(pl.Int64).alias("oi"), pl.col("NewBrdLotQty").cast(pl.Float64).cast(pl.Int64).alias("lot_size"),
        pl.lit("udiff").alias("src"), pl.lit(sha).alias("file_sha"))
