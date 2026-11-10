"""gold layer: processed signals (raw, z, z_neu), forward returns and cross-sectional context (PRD sections 4-6).

Everything is built from clipped silver loaders: while the lock is sealed no row after dev_end exists here.
Forward return: close t+1 -> close t+1+h, built from compounded daily total returns of sessions t+2..t+1+h; it needs a
traded row on t+1 (the fill) and on t+1+h (the exit). `label_end_date` is the date of session t+1+h.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path

import polars as pl
import yaml

from qr.eval.neutralize import dimson_beta, neutralize, winsor_z
from qr.guard.trial_ledger import git_state
from qr.panel import io
from qr.signals.registry import REGISTRY, compute_all, dense_panel

ROOT = Path(__file__).resolve().parents[3]
CFG = yaml.safe_load((ROOT / "config" / "research.yaml").read_text())


def forward_returns(dense: pl.LazyFrame, horizons: list[int], keep: pl.DataFrame | None = None) -> pl.LazyFrame:
    """`keep` (trade_date, sid) restricts output rows only (values are computed on the full per-sid history); horizons are
    collected one at a time to bound memory (D-031)."""
    d = dense.sort("sid", "sess").with_columns(pl.col("lret").fill_null(0.0).cum_sum().over("sid").alias("_cs"))
    outs = []
    for h in horizons:
        S = pl.col("_cs").shift(-(h + 1)).over("sid") - pl.col("_cs").shift(-1).over("sid")
        ok = pl.col("traded_row").shift(-1).over("sid") & pl.col("traded_row").shift(-(h + 1)).over("sid") & pl.col("traded_row")
        f = d.select("trade_date", "sid", pl.lit(h).cast(pl.Int32).alias("h"),
                     pl.when(ok).then(S.exp() - 1.0).otherwise(None).alias("fwd_ret"),
                     pl.col("trade_date").shift(-(h + 1)).over("sid").alias("label_end_date")).filter(pl.col("fwd_ret").is_not_null())
        if keep is not None:
            f = f.join(keep.lazy(), on=["trade_date", "sid"], how="semi")
        outs.append(f.collect().lazy())
    return pl.concat(outs)


def build_gold(silver: Path = Path("data/silver"), gold: Path = Path("data/gold")) -> dict:
    gold = Path(gold)
    prices, cal, bench = io.load_prices(silver), io.load_calendar(silver), io.load_bench(silver)
    uni = io.load_universe(silver).filter(pl.col("in_univ")).select("month_start", "sid", "rank_liq", "med_value_63d", "in_fno")
    sectors = io.load_sectors(silver)
    dense = dense_panel(prices, cal, bench)
    month = cal.with_columns(pl.col("trade_date").dt.year().alias("y"), pl.col("trade_date").dt.month().alias("m")).with_columns(
        pl.col("trade_date").min().over("y", "m").alias("month_start")).select("trade_date", "month_start")
    keep = month.join(uni.select("month_start", "sid"), on="month_start").filter(
        pl.col("trade_date") >= pl.lit(CFG["dev"]["start"]).str.to_date()).select("trade_date", "sid")
    raw = compute_all(dense, keep=keep)  # same rows as the universe/dev join below, filtered early to bound memory
    # restrict to dev dates and to the PIT universe of the month containing t
    raw = raw.join(month, on="trade_date").join(uni, on=["month_start", "sid"]).filter(
        (pl.col("trade_date") >= pl.lit(CFG["dev"]["start"]).str.to_date()))
    sig = winsor_z(raw.select("trade_date", "sid", "signal", "raw"))
    beta = dimson_beta(dense).join(keep.lazy(), on=["trade_date", "sid"], how="semi").collect()
    ctx = (raw.select("trade_date", "sid", "month_start", "rank_liq", "med_value_63d", "in_fno").unique(["trade_date", "sid"])
           .join(beta, on=["trade_date", "sid"], how="left").join(sectors.select("sid", "industry"), on="sid", how="left")
           .with_columns(pl.col("industry").fill_null("Unclassified"), pl.col("med_value_63d").log().alias("size")))
    # neutralize one signal at a time (it works per (signal, date) anyway): same values, bounded memory
    cx = ctx.select("trade_date", "sid", "industry", "beta", "size")
    parts = []
    for n in sig["signal"].unique(maintain_order=True).to_list():
        s_n = sig.filter(pl.col("signal") == n)
        neu = neutralize(s_n.select("trade_date", "sid", "signal", "z"), cx)
        parts.append(s_n.join(neu.select("trade_date", "sid", "signal", "z_neu"), on=["trade_date", "sid", "signal"], how="left"))
        del s_n, neu
    signals = pl.concat(parts)
    del sig, parts, raw, prices  # write each output as soon as it is ready and drop it: the full panel needs < 7 GB RAM (D-031)
    rows = {}

    def _write(name: str, df: pl.DataFrame) -> None:
        (gold / name).mkdir(parents=True, exist_ok=True)
        df.write_parquet(gold / name / f"{name}.parquet", compression="zstd")
        rows[name] = df.height

    # standardized neutral score already re-standardized per date inside neutralize_one_date
    _write("signals", signals)
    max_date = str(signals["trade_date"].max())
    del signals
    _write("context", ctx)
    fwd = forward_returns(dense, CFG["horizons"], keep=keep).collect().join(ctx.select("trade_date", "sid"), on=["trade_date", "sid"]).with_columns(
        (pl.col("fwd_ret") - pl.col("fwd_ret").mean().over("trade_date", "h")).alias("fwd_ret_xs"))
    _write("fwd_returns", fwd)
    sha, dirty = git_state()
    man = {"git_sha": sha, "dirty": dirty, "rows": rows, "built_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           "config_hash": hashlib.sha256((ROOT / "config" / "research.yaml").read_bytes()).hexdigest()[:16],
           "max_trade_date": max_date, "signals": list(REGISTRY)}
    (gold / "_manifest.json").write_text(json.dumps(man, indent=1))
    return man
