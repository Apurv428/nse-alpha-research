"""Freeze the headline model BEFORE the OOS window is opened (PRD section 9).

Trains the pre-registered headline combiner once on all development data (expanding window ending GAP sessions before
the first OOS session; labels already end on or before dev_end because gold is read through the clipped loaders), writes
config/frozen/frozen.json (+ lgbm.txt) and records the model name, portfolio config and the artifact hash in oos.lock.
Run while the lock is sealed; the frozen files are committed and the OOS run only loads them.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import polars as pl

from qr.guard import oos_lock
from qr.models import combiners as C
from qr.models import cv
from qr.models.run import FEATURES, restandardize, wide_features
from qr.panel import io

FROZEN_DIR = Path(__file__).resolve().parents[3] / "config" / "frozen"
PORTFOLIO_CONFIG = {"P1": {"enter": 0.10, "keep": 0.20, "cap_adv": 0.10, "rebalance": "weekly, signal t close, fill t+1 close", "benchmark": "Nifty 500 TRI"},
                    "P2": {"long": "top quintile cash", "short": "bottom quintile near-month futures", "roll_sessions": 3, "margin": 0.20},
                    "costs": "config/costs.yaml", "Y": 1.0, "aum_cr": 1.0, "rf_annual": 0.065}


def _sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def fit_final(sig: pl.DataFrame, fwd: pl.DataFrame, ctx: pl.DataFrame, cal: pl.DataFrame, model: str, out_dir: Path) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    meta = {"model": model, "features": FEATURES, "target": "gaussian cross-sectional rank of 5d fwd return"}
    if model != "EW":
        X, _ = wide_features(sig, ctx)
        f5 = fwd.filter(pl.col("h") == 5).select("trade_date", "sid", "fwd_ret")
        data = X.join(f5, on=["trade_date", "sid"], how="left")
        data = data.with_columns(pl.Series("y", C.gaussian_rank_target(data, "fwd_ret"))).with_columns(
            pl.when(pl.col("fwd_ret").is_null()).then(None).otherwise(pl.col("y")).alias("y")).join(cal, on="trade_date")
        last = int(cal["sess"].max())
        train_end_sess = last + 1 - cv.GAP          # the first OOS session is last+1
        train_end = cal.filter(pl.col("sess") == train_end_sess)["trade_date"].item()
        fold = {"train_start": cal.filter(pl.col("trade_date") >= pl.lit("2013-02-01").str.to_date())["trade_date"].min(), "train_end": train_end}
        tr_sess = cv.train_sessions(cal, fold)
        inner, val = cv.inner_split(tr_sess)
        take = lambda a: data.filter(pl.col("sess").is_in(a.tolist()) & pl.col("y").is_not_null())
        tr, inn, vl = take(tr_sess), take(inner), take(val)
        mat = lambda d: d.select(FEATURES).to_numpy()
        meta.update(train_start=str(fold["train_start"]), train_end=str(train_end), n_train=tr.height)
        if model == "RIDGE":
            m, info = C.fit_ridge(mat(tr), tr["y"].to_numpy(), mat(inn), inn["y"].to_numpy(), mat(vl), vl["y"].to_numpy())
            meta.update(alpha=info["alpha"], coef=info["coef"])
        else:
            m, info = C.fit_lgbm(mat(tr), tr["y"].to_numpy(), mat(inn), inn["y"].to_numpy(), mat(vl), vl["y"].to_numpy(), FEATURES)
            (out_dir / "lgbm.txt").write_text(m.model_to_string())
            meta.update(best_iteration=info["best_iteration"], lgbm_sha256=_sha(out_dir / "lgbm.txt"))
    (out_dir / "frozen.json").write_text(json.dumps(meta, indent=1, default=str))
    return meta


def load_frozen(frozen_dir: Path = FROZEN_DIR) -> dict:
    meta = json.loads((Path(frozen_dir) / "frozen.json").read_text())
    if meta["model"] == "LGBM":
        import lightgbm as lgb
        meta["_booster"] = lgb.Booster(model_str=(Path(frozen_dir) / "lgbm.txt").read_text())
    return meta


def score(meta: dict, X: pl.DataFrame) -> pl.DataFrame:
    """(trade_date, sid, score) re-standardized per date. X from `wide_features` (missing z already 0)."""
    M = X.select(FEATURES).to_numpy()
    s = C.ew_score(M) if meta["model"] == "EW" else (M @ np.array(meta["coef"]) if meta["model"] == "RIDGE" else meta["_booster"].predict(M))
    sc = X.select("trade_date", "sid").with_columns(pl.Series("score", s))
    return restandardize(sc, "score").filter(pl.col("score").is_not_null() & pl.col("score").is_finite())


def freeze(combo_dir: Path, gold: Path = Path("data/gold"), silver: Path = Path("data/silver"), out_dir: Path = FROZEN_DIR,
           lock_path: Path = oos_lock.LOCK_PATH) -> dict:
    if oos_lock.state(lock_path) != "sealed":
        raise oos_lock.OOSLockError("freeze only while sealed")
    model = json.loads((Path(combo_dir) / "selection.json").read_text())["headline"]
    meta = fit_final(io.load_gold("signals", gold), io.load_gold("fwd_returns", gold), io.load_gold("context", gold),
                     io.load_calendar(silver), model, out_dir)
    cfg = {**PORTFOLIO_CONFIG, "frozen_sha256": _sha(Path(out_dir) / "frozen.json"), "combo_run": Path(combo_dir).name}
    oos_lock.set_headline(model, cfg, lock_path)
    return {"frozen": meta, "portfolio": cfg}
