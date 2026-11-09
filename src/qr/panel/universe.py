"""silver.universe: monthly point-in-time liquidity universe (PRD section 4).

Rebuilt on the first session of each month using data up to the PRIOR close only. A sid is in the universe when:
series EQ/BE; >=252 sessions past its first trade; traded on >=55 of the last 63 sessions; raw close >= Rs 10;
63-session median traded value >= Rs 1 crore; and it ranks in the top 750 by that median.
Windows count NSE sessions; a missing session is a missing observation, not a zero.
Demerger exclusion uses only PAST events (ex-date within the last 5 sessions): a future ex-date is not
point-in-time information in our data (DECISIONS D-011).
"""
from __future__ import annotations

import polars as pl


def month_starts(calendar: pl.DataFrame) -> pl.DataFrame:
    """First session of each calendar month, with the session index S of the prior close."""
    c = calendar.with_columns(pl.col("trade_date").dt.year().alias("y"), pl.col("trade_date").dt.month().alias("m"))
    first = c.group_by("y", "m").agg(month_start=pl.col("trade_date").min(), sess0=pl.col("sess").min()).sort("month_start")
    prev = calendar.rename({"trade_date": "asof_date", "sess": "S"})
    return first.with_columns((pl.col("sess0") - 1).alias("S")).filter(pl.col("S") >= 0).join(prev, on="S").select(
        "month_start", "asof_date", "S")


def build_universe(prices: pl.DataFrame, calendar: pl.DataFrame, fo: pl.DataFrame | None, master: pl.DataFrame,
                   cfg: dict) -> pl.DataFrame:
    u = cfg["universe"]
    W, min_tr = int(u["window"]), int(u["min_traded_63"])
    p = prices.select("sid", "sess", "trade_date", "series", "close", "value_inr", "has_demerger").sort("sess")
    first_sess = p.group_by("sid").agg(first_sess=pl.col("sess").min())
    dem = p.filter(pl.col("has_demerger")).select("sid", pl.col("sess").alias("dem_sess"))
    # symbol -> sid for the F&O flag (a symbol maps to a sid only inside that segment's valid dates)
    seg = master.select("symbol", "valid_from", "valid_to", "sid")
    out = []
    for ms in month_starts(calendar).iter_rows(named=True):
        S = ms["S"]
        w = p.filter((pl.col("sess") > S - W) & (pl.col("sess") <= S))
        if w.height == 0:
            continue
        g = (w.group_by("sid").agg(n_traded_63d=pl.len(), med_value_63d=pl.col("value_inr").median(),
                                   last_sess=pl.col("sess").max(),
                                   last_close=pl.col("close").sort_by("sess").last(),
                                   last_series=pl.col("series").sort_by("sess").last())
             .join(first_sess, on="sid").with_columns((S - pl.col("first_sess")).alias("age_sessions")))
        recent_dem = dem.filter((pl.col("dem_sess") <= S) & (pl.col("dem_sess") > S - 5)).select("sid").unique()
        g = g.filter(
            pl.col("last_series").is_in(u["tradable_series"]) & (pl.col("age_sessions") >= u["min_age_sessions"]) &
            (pl.col("n_traded_63d") >= min_tr) & (pl.col("last_close") >= u["min_close_inr"]) &
            (pl.col("med_value_63d") >= u["min_median_value_inr"])).join(recent_dem, on="sid", how="anti")
        g = g.sort("med_value_63d", descending=True).with_row_index("rank_liq").with_columns(
            (pl.col("rank_liq") + 1).cast(pl.Int64), (pl.col("rank_liq") < u["top_n"]).alias("in_univ"))
        if fo is not None and fo.height:
            futs = fo.filter(pl.col("trade_date") == ms["asof_date"]).select("symbol").unique().join(seg, on="symbol")
            futs = futs.filter((pl.col("valid_from") <= ms["asof_date"]) & (pl.col("valid_to") >= ms["asof_date"]))
            fo_sids = futs.select("sid").unique().with_columns(pl.lit(True).alias("in_fno"))
            g = g.join(fo_sids, on="sid", how="left").with_columns(pl.col("in_fno").fill_null(False))
        else:
            g = g.with_columns(pl.lit(False).alias("in_fno"))
        out.append(g.with_columns(pl.lit(ms["month_start"]).alias("month_start"), pl.lit(ms["asof_date"]).alias("asof_date")))
    return pl.concat(out).select("month_start", "asof_date", "sid", "rank_liq", "med_value_63d", "n_traded_63d",
                                 "age_sessions", "in_univ", "in_fno", "last_series", "last_close")
