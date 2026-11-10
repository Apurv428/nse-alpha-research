"""silver.prices: split/bonus/dividend-adjusted total returns and the jump audit (PRD section 4).

r_t = (P_t + D_t) / (f_t * P_s) - 1, s = previous session this sid traded, f_t = product of price factors of the
events with ex-date in (s, t]. Where no exported event explains day t, f_t is inferred from the exchange's own adjusted
previous close in the day-t bhavcopy (optional, off by default: real files show PREVCLOSE is NOT split-adjusted, D-023).
Ratio snapping (PRD s11 fallback, D-023): a flagged |r| > 25% day with no export event whose price ratio P_t / P_s lies within
SNAP_TOL of a common split/bonus/consolidation ratio is treated as that action (f_t = ratio). A non-matching jump is a genuine move
for F&O stocks (no price band) and is kept; for other stocks (bands <= 20%) it cannot be a one-day move and is nulled and logged. Signals use returns and INR traded value only; no adjusted price level exists.
Only raw prices are used for level filters (universe). Everything at row t uses information up to t.
"""
from __future__ import annotations

import polars as pl

from qr.panel.master import attach_sid

FACTOR_TOL = 0.01      # exchange-implied factor |f - 1| above this counts as a corporate-action adjustment (D-023)
FACTOR_RANGE = (0.01, 100.0)
MISSING_SESSION_SHARE = 0.20  # if this share of names on a date shows a factor, the date follows a session we do not have
                              # (weekend special session, calendar hole): no inference that day
JUMP = 0.25
# split (face value 10->5/2/1, 5->1/2, 2->1) and bonus a:b -> b/(a+b) ratios, plus consolidations
SNAP_RATIOS = [1 / 10, 1 / 5, 1 / 4, 1 / 3, 2 / 5, 1 / 2, 3 / 5, 2 / 3, 3 / 4, 2.0, 5.0, 10.0]
SNAP_TOL = 0.12   # |ratio / c - 1|; the nearest c wins  # |r| above this with no explanation is a flagged jump (PRD: NSE bands cap most names at 20%)
UNADJUSTED = ["rights", "split_unparsed", "bonus_unparsed", "dividend_unparsed"]


EVIDENCE_TOL = 0.10
SUSPECT_OI_RATIO = 1.8   # F&O jump with no ratio match but OI up >= 1.8x and lot unchanged: demerger-like adjustment -> null   # F&O names: snap only if lot (or OI) moved by ~1/c: |ratio * c - 1| < this


def fno_evidence(fo: pl.DataFrame) -> pl.DataFrame:
    """(trade_date, symbol, lot_ratio, oi_ratio) from stock-futures rows. lot = traded value / (contracts * close) for the most
    traded contract alive on both days; NSE changes the lot of EXISTING contracts only for a corporate action. oi_ratio = OI today /
    OI yesterday of contracts still alive today (expiring contracts excluded). Both are known at day t's close (PIT)."""
    f = fo.filter((pl.col("contracts") > 0) & (pl.col("close") > 0) & (pl.col("value_inr") > 0)).with_columns(
        (pl.col("value_inr") / (pl.col("contracts") * pl.col("close"))).alias("_lot"))
    f = f.sort("symbol", "expiry", "trade_date").with_columns(
        (pl.col("_lot") / pl.col("_lot").shift(1).over("symbol", "expiry")).alias("_lr"),
        pl.col("trade_date").shift(1).over("symbol", "expiry").alias("_pd"))
    lot = (f.filter(pl.col("_lr").is_not_null()).sort("contracts", descending=True)
           .group_by("symbol", "trade_date").agg(pl.col("_lr").first().alias("lot_ratio"), pl.col("_pd").first().alias("_pd")))
    o = fo.select("symbol", "trade_date", "expiry", "oi")
    days = o.select("trade_date").unique().sort("trade_date").with_columns(pl.col("trade_date").shift(1).alias("prev_date"))
    today = o.group_by("symbol", "trade_date").agg(oi_t=pl.col("oi").sum()).join(days, on="trade_date")
    prev = (o.join(days, left_on="trade_date", right_on="prev_date", suffix="_next")
            .filter(pl.col("expiry") >= pl.col("trade_date_next"))
            .group_by("symbol", "trade_date_next").agg(oi_p=pl.col("oi").sum()).rename({"trade_date_next": "trade_date"}))
    oi = today.join(prev, on=["symbol", "trade_date"], how="left").with_columns((pl.col("oi_t") / pl.col("oi_p")).alias("oi_ratio"))
    return oi.join(lot, on=["symbol", "trade_date"], how="full", coalesce=True).select("trade_date", "symbol", "lot_ratio", "oi_ratio")


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
                 events: pl.DataFrame | None = None, infer_from_exchange: bool = False,
                 fno_days: pl.DataFrame | None = None, snap_ratios: bool = True) -> tuple[pl.DataFrame, pl.DataFrame, dict]:
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
    f_ex = pl.col("prev_close") / pl.col("_pc")
    cand = ((pl.col("n_events") == 0) & (pl.col("_pc") > 0) & (pl.col("prev_close") > 0)
            & ((f_ex - 1).abs() > FACTOR_TOL) & (f_ex > FACTOR_RANGE[0]) & (f_ex < FACTOR_RANGE[1]))
    p = p.with_columns(cand.fill_null(False).alias("_cand"))
    share = pl.col("_cand").filter(pl.col("_pc") > 0).mean().over("trade_date")
    n_px = (pl.col("_pc") > 0).sum().over("trade_date")
    p = p.with_columns(((share > MISSING_SESSION_SHARE) & (n_px >= 20)).fill_null(False).alias("_missing_session"))
    missing_dates = p.filter(pl.col("_missing_session")).select("trade_date").unique().sort("trade_date")["trade_date"].to_list()
    use_ex = pl.lit(infer_from_exchange) & pl.col("_cand") & ~pl.col("_missing_session")
    p = p.with_columns(pl.when(use_ex).then(pl.lit("exchange")).when(pl.col("n_events") > 0).then(pl.lit("export"))
                       .otherwise(None).alias("factor_source"),
                       pl.when(use_ex).then(f_ex).otherwise(pl.col("price_factor")).alias("price_factor"))
    ok = (pl.col("_pc") > 0) & (pl.col("close") > 0)
    p = p.with_columns(
        pl.when(ok).then((pl.col("close") + pl.col("div_inr")) / (pl.col("price_factor") * pl.col("_pc")) - 1.0)
        .otherwise(None).alias("_ret"))
    if fno_days is not None and fno_days.height:
        ev_fo = fno_evidence(fno_days) if "contracts" in fno_days.columns else fno_days.select("trade_date", "symbol").unique().with_columns(
            pl.lit(None, pl.Float64).alias("lot_ratio"), pl.lit(None, pl.Float64).alias("oi_ratio"))
        p = p.join(ev_fo.with_columns(pl.lit(True).alias("_fno")), on=["trade_date", "symbol"], how="left")
    else:
        p = p.with_columns(pl.lit(None, pl.Boolean).alias("_fno"), pl.lit(None, pl.Float64).alias("lot_ratio"),
                           pl.lit(None, pl.Float64).alias("oi_ratio"))
    p = p.with_columns(pl.col("_fno").fill_null(False))
    if snap_ratios:
        q = (pl.col("close") / pl.col("_pc"))
        cands = [((q / c - 1).abs(), c) for c in SNAP_RATIOS]
        best_err = pl.min_horizontal([e for e, _ in cands])
        best_c = pl.lit(None, pl.Float64)
        for e, c in reversed(cands):
            best_c = pl.when(e == best_err).then(pl.lit(c)).otherwise(best_c)
        # F&O names have no price band, so a ratio match alone is not enough: require the lot (else OI) to have moved by ~1/c
        evid = pl.coalesce((pl.col("lot_ratio") * best_c - 1).abs(), (pl.col("oi_ratio") * best_c - 1).abs()) < EVIDENCE_TOL
        # never across a hole in the market calendar (> 7 calendar days since the previous session): data gap, not an action
        calgap = calendar.sort("trade_date").with_columns((pl.col("trade_date") - pl.col("trade_date").shift(1)).dt.total_days().alias("_cal_gap"))
        p = p.join(calgap.select("trade_date", "_cal_gap"), on="trade_date", how="left")
        snap = ((pl.col("_ret").abs() > JUMP) & (pl.col("n_events") == 0) & (pl.col("gap_days") == 0) & (best_err < SNAP_TOL)
                & (pl.col("_cal_gap").fill_null(99) <= 7)
                & (~pl.col("_fno") | evid.fill_null(False)))
        p = p.with_columns(snap.fill_null(False).alias("_snap"), best_c.alias("_c"))
        p = p.with_columns(pl.when(pl.col("_snap")).then(pl.col("_c")).otherwise(pl.col("price_factor")).alias("price_factor"),
                           pl.when(pl.col("_snap")).then(pl.lit("ratio_snap")).otherwise(pl.col("factor_source")).alias("factor_source"))
        p = p.with_columns(pl.when(pl.col("_snap")).then(pl.col("close") / (pl.col("price_factor") * pl.col("_pc")) - 1.0)
                           .otherwise(pl.col("_ret")).alias("_ret"))
    else:
        p = p.with_columns(pl.lit(False).alias("_snap"))
    big = pl.col("_ret").abs() > JUMP
    resolution = (pl.when(pl.col("has_demerger") & pl.col("_ret").is_not_null()).then(pl.lit("demerger_nulled"))
                  .when(big & (pl.col("gap_days") > 0)).then(pl.lit("halt_gap_kept"))
                  .when(big & pl.col("has_unadjusted")).then(pl.lit("unadjusted_event_nulled"))
                  .when(big & (pl.col("price_factor") != 1.0)).then(pl.lit("action_residual_nulled"))
                  .when(big & pl.col("_fno") & (pl.col("oi_ratio") >= SUSPECT_OI_RATIO)).then(pl.lit("fno_suspect_action_nulled"))
                  .when(big & pl.col("_fno")).then(pl.lit("fno_genuine_kept"))
                  .when(big).then(pl.lit("unexplained_nulled"))
                  .when(pl.col("_snap")).then(pl.lit("ratio_snapped")).otherwise(None))
    p = p.with_columns(resolution.alias("resolution"))
    p = p.with_columns(pl.when(pl.col("resolution").is_in(
        ["demerger_nulled", "unadjusted_event_nulled", "action_residual_nulled", "unexplained_nulled", "fno_suspect_action_nulled"]))
        .then(None).otherwise(pl.col("_ret")).alias("ret_1d"))
    audit = p.filter(pl.col("resolution").is_not_null()).select(
        "trade_date", "sid", "symbol", "isin", "series", "close", pl.col("_pc").alias("prev_close_own"),
        "price_factor", "div_inr", "gap_days", pl.col("_ret").alias("ret_unnulled"), "resolution", "value_inr", "_fno", "lot_ratio", "oi_ratio")
    p = p.with_columns((pl.col("value_inr") > 0).alias("traded")).select(
        "trade_date", "sid", "symbol", "isin", "series", "open", "high", "low", "close", "last", "prev_close",
        "value_inr", "volume_sh", "n_trades", "deliv_pct", "price_factor", "div_inr", "ret_1d", "traded",
        "gap_days", "sess", "src", "has_demerger", "factor_source")
    stats = {"rows_in": n0, "rows_out": p.height, "duplicate_sid_day_rows_dropped": n_dup,
             "rows_with_null_sid": int(p["sid"].is_null().sum()),
             "n_exchange_factors": int((p["factor_source"] == "exchange").sum()),
             "n_export_factor_days": int((p["factor_source"] == "export").sum()),
             "n_ratio_snapped": int((p["factor_source"] == "ratio_snap").sum()),
             "missing_session_dates": [str(d) for d in missing_dates] if infer_from_exchange else []}
    return p, audit, stats
