"""silver.prices: split/bonus/dividend-adjusted total returns and the jump audit (PRD section 4).

r_t = (P_t + D_t) / (f_t * P_s) - 1, s = previous session this sid traded, f_t = product of price factors of the
events with ex-date in (s, t]. Signals use returns and INR traded value only; no adjusted price level exists.
Only raw prices are used for level filters (universe). Everything at row t uses information up to t.
"""
from __future__ import annotations

import polars as pl

from qr.panel.master import attach_sid

JUMP = 0.25  # |r| above this with no explanation is a flagged jump (PRD: NSE bands cap most names at 20%)
UNADJUSTED = ["rights", "split_unparsed", "bonus_unparsed", "dividend_unparsed"]


def map_events_to_sid(ca: pl.DataFrame, master: pl.DataFrame) -> tuple[pl.DataFrame, int]:
    """Map each corporate action (symbol, ex_date) to the sid whose symbol segment contains the ex-date.
    Falls back to the nearest segment within 10 calendar days. Returns (events with sid, n_unmapped)."""
    import datetime as dt

    seg: dict[str, list] = {}
    for r in master.select("symbol", "valid_from", "valid_to", "sid").iter_rows():
        seg.setdefault(r[0], []).append(r[1:])
    sids, bad = [], 0
    for sym, ex in ca.select("symbol", "ex_date").iter_rows():
        best = None
        for vf, vt, sid in seg.get(sym, []):
            if vf <= ex <= vt:
                best = (0, sid)
                break
            d = (vf - ex).days if ex < vf else (ex - vt).days
            if d <= 10 and (best is None or d < best[0]):
                best = (d, sid)
        sids.append(best[1] if best else None)
        bad += best is None
    return ca.with_columns(pl.Series("sid", sids, dtype=pl.Int64)).filter(pl.col("sid").is_not_null()), bad


def assign_events(ev: pl.DataFrame, keys: pl.DataFrame) -> pl.DataFrame:
    """Attach each event to the first session >= ex_date on which its sid traded; aggregate per (sid, trade_date)."""
    if ev.height == 0:
        return pl.DataFrame(schema={"sid": pl.Int64, "trade_date": pl.Date, "price_factor": pl.Float64,
                                    "div_inr": pl.Float64, "has_demerger": pl.Boolean, "has_unadjusted": pl.Boolean,
                                    "n_events": pl.UInt32})
    j = (ev.sort("ex_date").join_asof(keys.sort("trade_date"), left_on="ex_date", right_on="trade_date",
                                      by="sid", strategy="forward", check_sortedness=False).filter(pl.col("trade_date").is_not_null()))
    return j.group_by("sid", "trade_date").agg(
        price_factor=pl.col("price_factor").fill_null(1.0).product(),
        div_inr=pl.col("cash_inr").fill_null(0.0).sum(),
        has_demerger=(pl.col("action") == "demerger").any(),
        has_unadjusted=pl.col("action").is_in(UNADJUSTED).any(),
        n_events=pl.len())


def build_prices(cm: pl.DataFrame, mto: pl.DataFrame, pair_map: pl.DataFrame, calendar: pl.DataFrame,
                 events: pl.DataFrame | None = None) -> tuple[pl.DataFrame, pl.DataFrame, dict]:
    """Returns (prices, jump_audit, stats). `events` already carries sid (see map_events_to_sid)."""
    cm = attach_sid(cm, pair_map)
    n0 = cm.height
    cm = cm.sort("value_inr", descending=True, nulls_last=True).unique(subset=["trade_date", "sid"], keep="first")
    n_dup = n0 - cm.height
    cm = cm.join(calendar, on="trade_date", how="left")
    if mto is not None and mto.height:
        d = mto.select("trade_date", "symbol", "series", "deliv_pct").unique(subset=["trade_date", "symbol", "series"])
        cm = cm.join(d, on=["trade_date", "symbol", "series"], how="left")
    else:
        cm = cm.with_columns(pl.lit(None, pl.Float64).alias("deliv_pct"))
    cm = cm.sort("sid", "trade_date")
    ev = assign_events(events, cm.select("sid", "trade_date")) if events is not None else assign_events(pl.DataFrame(), cm)
    p = cm.join(ev, on=["sid", "trade_date"], how="left").with_columns(
        pl.col("price_factor").fill_null(1.0), pl.col("div_inr").fill_null(0.0),
        pl.col("has_demerger").fill_null(False), pl.col("has_unadjusted").fill_null(False),
        pl.col("n_events").fill_null(0))
    p = p.sort("sid", "trade_date").with_columns(
        pl.col("close").shift(1).over("sid").alias("_pc"),
        (pl.col("sess") - pl.col("sess").shift(1).over("sid") - 1).alias("gap_days"))
    ok = (pl.col("_pc") > 0) & (pl.col("close") > 0)
    p = p.with_columns(
        pl.when(ok).then((pl.col("close") + pl.col("div_inr")) / (pl.col("price_factor") * pl.col("_pc")) - 1.0)
        .otherwise(None).alias("_ret"))
    big = pl.col("_ret").abs() > JUMP
    resolution = (pl.when(pl.col("has_demerger") & pl.col("_ret").is_not_null()).then(pl.lit("demerger_nulled"))
                  .when(big & (pl.col("gap_days") > 0)).then(pl.lit("halt_gap_kept"))
                  .when(big & pl.col("has_unadjusted")).then(pl.lit("unadjusted_event_nulled"))
                  .when(big & (pl.col("price_factor") != 1.0)).then(pl.lit("action_residual_nulled"))
                  .when(big).then(pl.lit("unexplained_nulled")).otherwise(None))
    p = p.with_columns(resolution.alias("resolution"))
    p = p.with_columns(pl.when(pl.col("resolution").is_in(
        ["demerger_nulled", "unadjusted_event_nulled", "action_residual_nulled", "unexplained_nulled"]))
        .then(None).otherwise(pl.col("_ret")).alias("ret_1d"))
    audit = p.filter(pl.col("resolution").is_not_null()).select(
        "trade_date", "sid", "symbol", "isin", "series", "close", pl.col("_pc").alias("prev_close_own"),
        "price_factor", "div_inr", "gap_days", pl.col("_ret").alias("ret_unnulled"), "resolution")
    p = p.with_columns((pl.col("value_inr") > 0).alias("traded")).select(
        "trade_date", "sid", "symbol", "isin", "series", "open", "high", "low", "close", "last", "prev_close",
        "value_inr", "volume_sh", "n_trades", "deliv_pct", "price_factor", "div_inr", "ret_1d", "traded",
        "gap_days", "sess", "src", "has_demerger")
    stats = {"rows_in": n0, "rows_out": p.height, "duplicate_sid_day_rows_dropped": n_dup,
             "rows_with_null_sid": int(p["sid"].is_null().sum())}
    return p, audit, stats
