"""silver.bench (Nifty 500 close and total-return index) and silver.sectors (PRD sections 3, 4)."""
from __future__ import annotations

from pathlib import Path

import polars as pl

N500_NAMES = ["Nifty 500", "NIFTY 500", "S&P CNX 500", "CNX 500"]  # renamed in/around 2013-2015 (DECISIONS D-009)


def build_bench(index_daily: pl.DataFrame, manual_tri: Path | None = None) -> pl.DataFrame:
    """Approximate TRI: TRI_t = TRI_{t-1} * (P_t/P_{t-1} + DY_{t-1}/25200), DY in %. Always labelled approximate
    unless a manually exported official TRI file is supplied."""
    n = (index_daily.filter(pl.col("index_name").is_in(N500_NAMES)).sort("trade_date")
         .unique(subset=["trade_date"], keep="first", maintain_order=True).select("trade_date", "close", "div_yield_pct"))
    n = n.rename({"close": "n500_close"})
    dy = pl.col("div_yield_pct").shift(1).fill_null(0.0)
    growth = (pl.col("n500_close") / pl.col("n500_close").shift(1) + dy / 25200.0).fill_null(1.0)
    out = n.with_columns(growth.cum_prod().mul(100.0).alias("n500_tri"), pl.lit(True).alias("tri_is_approx"))
    if manual_tri is not None and Path(manual_tri).exists():
        t = pl.read_csv(manual_tri, try_parse_dates=True)  # columns: trade_date, n500_tri
        out = out.drop("n500_tri", "tri_is_approx").join(t.select("trade_date", "n500_tri"), on="trade_date", how="left")\
            .with_columns(pl.lit(False).alias("tri_is_approx"))
    return out.select("trade_date", "n500_close", "n500_tri", "tri_is_approx", "div_yield_pct")


SECTOR_FILES = ["ind_nifty500list.csv", "ind_niftytotalmarket_list.csv", "ind_niftymidcap150list.csv",
                "ind_niftysmallcap250list.csv", "ind_niftymicrocap250_list.csv"]  # priority order


def build_sectors(master: pl.DataFrame, static_dir: Path, snapshot_dates: dict[str, str]) -> pl.DataFrame:
    """Industry per sid from the CURRENT index-constituent snapshots (not point-in-time). Match by ISIN, then symbol;
    everything else is `Unclassified` and acts as its own sector in neutralization."""
    frames = []
    for pri, fn in enumerate(SECTOR_FILES):
        p = Path(static_dir) / fn
        if p.exists():
            df = pl.read_csv(p, infer_schema_length=0).rename({c: c.strip() for c in pl.read_csv(p, infer_schema_length=0, n_rows=0).columns})
            frames.append(df.select(pl.col("Industry").alias("industry"), pl.col("Symbol").alias("symbol"),
                                    pl.col("ISIN Code").alias("isin"), pl.lit(fn).alias("source_file"), pl.lit(pri).alias("pri")))
    if not frames:
        return master.select("sid").unique().with_columns(pl.lit("Unclassified").alias("industry"),
                                                           pl.lit(None, pl.String).alias("source_file"), pl.lit(None, pl.String).alias("snapshot_date"))
    lab = pl.concat(frames).sort("pri")
    by_isin = master.join(lab, on="isin").select("sid", "industry", "source_file", "pri")
    by_sym = master.join(lab, on="symbol").select("sid", "industry", "source_file", "pri")
    m = (pl.concat([by_isin, by_sym]).sort("pri").group_by("sid", maintain_order=True).first())
    allsid = master.select("sid").unique()
    out = allsid.join(m, on="sid", how="left").with_columns(
        pl.col("industry").fill_null("Unclassified"),
        pl.col("source_file"),
        pl.col("source_file").replace_strict(snapshot_dates, default=None).alias("snapshot_date"))
    return out.select("sid", "industry", "source_file", "snapshot_date").sort("sid")
