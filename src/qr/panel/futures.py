"""silver.fut_cont: near-month stock-future series with the roll rule (PRD sections 3, 4, 8).

Expiries are read from the files, never computed. On each date t the held contract is the nearest expiry that is at
least ROLL_SESSIONS sessions away (the short leg rolls 3 sessions before expiry). `ret_1d_fut` is the return realised
on t by the contract held at t-1: settle_t / (f_t * settle_{t-1}) - 1, with f_t the cash-market price factor so
exchange adjustments on ex-dates do not create fake futures returns. `roll_flag` marks days where the held contract changes.
"""
from __future__ import annotations

import polars as pl

ROLL_SESSIONS = 3


def build_fut_cont(fo: pl.DataFrame, calendar: pl.DataFrame, master: pl.DataFrame, prices: pl.DataFrame) -> pl.DataFrame:
    sess = calendar.select("trade_date", "sess")
    # symbol -> sid by validity segment
    seg = master.select("symbol", "valid_from", "valid_to", "sid")
    f = (fo.join(sess, on="trade_date").join(seg, on="symbol")
         .filter((pl.col("trade_date") >= pl.col("valid_from")) & (pl.col("trade_date") <= pl.col("valid_to")))
         .drop("valid_from", "valid_to"))
    # session index of each expiry = number of sessions with date <= expiry (expiry may be a non-session date)
    cal_dates = calendar["trade_date"].sort()
    exp_sess = (pl.DataFrame({"expiry": f["expiry"].unique().sort()})
                .with_columns(pl.Series("exp_sess", cal_dates.search_sorted(pl.Series(f["expiry"].unique().sort()), side="right")) - 1))
    f = f.join(exp_sess, on="expiry").with_columns((pl.col("exp_sess") - pl.col("sess")).alias("sess_to_expiry"))
    held = (f.filter(pl.col("sess_to_expiry") >= ROLL_SESSIONS).sort("sid", "trade_date", "expiry")
            .group_by("sid", "trade_date", maintain_order=True).first()
            .select("sid", "trade_date", "sess", pl.col("expiry").alias("expiry_held"), "settle", "close", "lot_size"))
    # return of the contract held at t-1, realised on t
    prev = held.select("sid", pl.col("sess").alias("sess_p"), pl.col("expiry_held").alias("expiry_p"), pl.col("settle").alias("settle_p"))
    key = f.select("sid", "trade_date", "sess", "expiry", pl.col("settle").alias("settle_t"))
    r = (held.with_columns((pl.col("sess") - 1).alias("sess_p")).join(prev, on=["sid", "sess_p"], how="left")
         .join(key, left_on=["sid", "trade_date", "expiry_p"], right_on=["sid", "trade_date", "expiry"], how="left", suffix="_k"))
    fac = prices.select("sid", "trade_date", "price_factor")
    r = r.join(fac, on=["sid", "trade_date"], how="left").with_columns(pl.col("price_factor").fill_null(1.0))
    r = r.with_columns(
        pl.when((pl.col("settle_p") > 0) & (pl.col("settle_t") > 0))
        .then(pl.col("settle_t") / (pl.col("price_factor") * pl.col("settle_p")) - 1).otherwise(None).alias("ret_1d_fut"),
        (pl.col("expiry_held") != pl.col("expiry_p")).fill_null(False).alias("roll_flag"))
    return r.select("trade_date", "sid", "expiry_held", "settle", "ret_1d_fut", "roll_flag", "lot_size").sort("trade_date", "sid")
