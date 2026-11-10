"""`qr fit`: EW vs ridge vs LightGBM on the same 8 purged, embargoed walk-forward folds (PRD section 7).

The headline is chosen by the pre-registered rule, not by eye: the better of ridge/LightGBM by mean fold rank IC at
h = 5 becomes the headline only if it beats equal weight with a Newey-West t >= 2 on the daily IC difference; otherwise
equal weight is the headline. Every (model, fold) is logged as a trial before anything prints.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import numpy as np
import polars as pl
from scipy.stats import binomtest

from qr.eval import ic as I
from qr.eval import turnover as T
from qr.guard.trial_ledger import git_state, log_trial
from qr.models import combiners as C
from qr.models import cv
from qr.panel import io
from qr.signals.registry import REGISTRY
from qr.stats.newey_west import nw_tstat

FEATURES = list(REGISTRY)
MODELS = ["EW", "RIDGE", "LGBM"]
T_HURDLE_VS_EW = 2.0


def wide_features(sig: pl.DataFrame, ctx: pl.DataFrame) -> tuple[pl.DataFrame, dict]:
    """(trade_date, sid, f_<signal>...) of z_neu over the universe rows; a missing z is filled with 0 (fill rate reported)."""
    w = sig.filter(pl.col("z_neu").is_not_null()).select("trade_date", "sid", "signal", "z_neu").pivot(on="signal", index=["trade_date", "sid"], values="z_neu")
    base = ctx.select("trade_date", "sid").join(w, on=["trade_date", "sid"], how="left")
    fill = {f: float(base[f].is_null().mean()) for f in FEATURES}
    return base.with_columns([pl.col(f).fill_null(0.0) for f in FEATURES]).sort("trade_date", "sid"), fill


def restandardize(df: pl.DataFrame, col: str) -> pl.DataFrame:
    return df.with_columns(((pl.col(col) - pl.col(col).mean().over("trade_date")) / pl.col(col).std().over("trade_date")).alias(col))


def run_combine(gold: Path = Path("data/gold"), silver: Path = Path("data/silver"), out_root: Path = Path("runs"), log: bool = True) -> dict:
    sig, fwd, ctx = io.load_gold("signals", gold), io.load_gold("fwd_returns", gold), io.load_gold("context", gold)
    cal = io.load_calendar(silver)
    X, fill = wide_features(sig, ctx)
    f5 = fwd.filter(pl.col("h") == 5).select("trade_date", "sid", "fwd_ret")
    data = X.join(f5, on=["trade_date", "sid"], how="left")
    data = data.with_columns(pl.Series("y", C.gaussian_rank_target(data.with_columns(pl.col("fwd_ret")), "fwd_ret"))).with_columns(
        pl.when(pl.col("fwd_ret").is_null()).then(None).otherwise(pl.col("y")).alias("y"))
    dsess = data.join(cal, on="trade_date")
    folds = cv.make_folds(cal.filter(pl.col("trade_date") >= pl.lit("2013-02-01").str.to_date()))
    out = Path(out_root) / f"combo_{dt.datetime.now(dt.timezone.utc):%Y%m%dT%H%M%S}"
    out.mkdir(parents=True, exist_ok=True)
    wk = T.weekly_dates(cal)
    scores, ridge_info, lgbm_info = [], [], []
    for f in folds.iter_rows(named=True):
        tr_sess = cv.train_sessions(cal, f)
        inner_sess, val_sess = cv.inner_split(tr_sess)
        take = lambda sess_arr: dsess.filter(pl.col("sess").is_in(sess_arr.tolist()) & pl.col("y").is_not_null())
        tr, inn, val = take(tr_sess), take(inner_sess), take(val_sess)
        te = dsess.filter((pl.col("trade_date") >= f["test_start"]) & (pl.col("trade_date") <= f["test_end"]))
        mat = lambda d: d.select(FEATURES).to_numpy()
        base = te.select("trade_date", "sid")
        scores.append(base.with_columns(pl.Series("score", C.ew_score(mat(te))), pl.lit("EW").alias("model"), pl.lit(f["fold_id"]).alias("fold_id")))
        rm, ri = C.fit_ridge(mat(tr), tr["y"].to_numpy(), mat(inn), inn["y"].to_numpy(), mat(val), val["y"].to_numpy())
        scores.append(base.with_columns(pl.Series("score", rm.predict(mat(te))), pl.lit("RIDGE").alias("model"), pl.lit(f["fold_id"]).alias("fold_id")))
        ridge_info.append({"fold_id": f["fold_id"], "n_train": tr.height, "alpha": ri["alpha"], **{f"coef_{n}": c for n, c in zip(FEATURES, ri["coef"])}})
        gm, gi = C.fit_lgbm(mat(tr), tr["y"].to_numpy(), mat(inn), inn["y"].to_numpy(), mat(val), val["y"].to_numpy(), FEATURES)
        scores.append(base.with_columns(pl.Series("score", gm.predict(mat(te))), pl.lit("LGBM").alias("model"), pl.lit(f["fold_id"]).alias("fold_id")))
        lgbm_info.append({"fold_id": f["fold_id"], "n_train": tr.height, "best_iteration": gi["best_iteration"], **{f"gain_{n}": v for n, v in gi["gain"].items()}})
    sc = restandardize(pl.concat(scores), "score").filter(pl.col("score").is_not_null() & pl.col("score").is_finite())
    # ---- evaluation: per fold and pooled, h = 5 plus decay at 1/5/10/21 ----
    long = sc.select("trade_date", "sid", pl.col("model").alias("signal"), "score", "fold_id")
    ics = I.ic_series(long.select("trade_date", "sid", "signal", "score"), fwd, "score")
    fold_of = sc.select("trade_date", "fold_id").unique()
    fold_ids = sorted(int(x) for x in folds["fold_id"].to_list())
    ics = ics.join(fold_of, on="trade_date")
    rows = []
    for m in MODELS:
        for k in fold_ids + ["all"]:
            g = ics.filter((pl.col("signal") == m) & (pl.col("h") == 5))
            g = g if k == "all" else g.filter(pl.col("fold_id") == k)
            x = g.sort("trade_date")["rank_ic"].drop_nulls().to_numpy()
            nw = nw_tstat(x, 5)
            no = x[::5]
            rows.append({"fold_id": str(k), "model": m, "mean_rank_ic_h5": nw["mean"], "t_nw": nw["t_nw"], "n_dates": len(x),
                         "icir_ann": float(no.mean() / no.std(ddof=1) * np.sqrt(252 / 5)) if len(no) > 2 else float("nan")})
    summ = pl.DataFrame(rows)
    decay = I.summarize(ics.drop("fold_id"), "combo").filter(pl.col("h").is_in([1, 5, 10, 21])).pivot(on="h", index="signal", values="mean_rank_ic")
    # ---- comparison vs EW ----
    piv = ics.filter(pl.col("h") == 5).pivot(on="signal", index=["trade_date", "fold_id"], values="rank_ic").sort("trade_date").drop_nulls()
    comp = {}
    fold_means = {m: summ.filter((pl.col("model") == m) & (pl.col("fold_id") != "all"))["mean_rank_ic_h5"].to_numpy() for m in MODELS}
    bad = {m: int((~np.isfinite(v)).sum()) for m, v in fold_means.items() if not np.isfinite(v).all()}
    if bad:  # a NaN fold mean would make every comparison False and silently select EW
        raise ValueError(f"fold mean rank IC is not finite for {bad}: empty test fold or no scores; fix the data, do not select")
    for m in ("RIDGE", "LGBM"):
        diff = (piv[m] - piv["EW"]).to_numpy()
        nw = nw_tstat(diff, 5)
        wins = int((fold_means[m] > fold_means["EW"]).sum())
        comp[m] = {"mean_diff": nw["mean"], "t_nw_diff": nw["t_nw"], "folds_beating_ew": wins, "n_folds": len(fold_ids),
                   "sign_test_p": float(binomtest(wins, len(fold_ids), 0.5).pvalue), "mean_fold_ic": float(fold_means[m].mean())}
    cand = max(("RIDGE", "LGBM"), key=lambda m: comp[m]["mean_fold_ic"])
    ew_ic = float(fold_means["EW"].mean())
    beats = comp[cand]["mean_fold_ic"] > ew_ic and comp[cand]["t_nw_diff"] >= T_HURDLE_VS_EW
    headline = cand if beats else "EW"
    sel = {"headline": headline, "candidate": cand, "candidate_beats_ew": bool(beats), "rule": "better of ridge/lgbm by mean fold rank IC at h=5; "
           "must beat EW with NW t >= 2 on the daily IC difference, else EW", "comparison": comp, "ew_mean_fold_ic": ew_ic}
    # ---- log every (model, fold) as a trial BEFORE printing; P0 spread of the score on the fold's test weeks ----
    trial_ids = {}
    if log:
        for m in MODELS:
            for f in folds.iter_rows(named=True):
                s = long.filter((pl.col("signal") == m) & (pl.col("fold_id") == f["fold_id"])).select("trade_date", "sid", "signal", "score")
                sp = T.spread_series(T.deciles(s, f5, "score", wk)).select("date", "ret")
                r = summ.filter((pl.col("model") == m) & (pl.col("fold_id") == str(f["fold_id"]))).row(0, named=True)
                params = {"model": m, "fold": f["fold_id"], "features": FEATURES, "target": "gaussian cross-sectional rank of 5d fwd return",
                          "lgbm": C.LGBM_PARAMS if m == "LGBM" else None, "alphas": C.ALPHAS if m == "RIDGE" else None}
                rec = log_trial("combo", params, (str(f["test_start"]), str(f["test_end"])), "W", sp, r["mean_rank_ic_h5"], r["t_nw"])
                trial_ids[f"{m}|{f['fold_id']}"] = rec["trial_id"]
    summ.write_csv(out / "combo_summary.csv")
    decay.write_csv(out / "combo_decay.csv")
    pl.DataFrame(ridge_info).write_csv(out / "ridge_coefs.csv")
    pl.DataFrame(lgbm_info).write_csv(out / "lgbm_importance.csv")
    folds.write_csv(out / "folds.csv")
    sc.select("trade_date", "sid", "model", "fold_id", "score").write_parquet(out / "test_scores.parquet")
    (out / "selection.json").write_text(json.dumps(sel, indent=1, default=str))
    allr = lambda m: summ.filter((pl.col("model") == m) & (pl.col("fold_id") == "all")).row(0, named=True)
    metrics = {"git_sha": git_state()[0], "combo.headline": headline, "combo.headline.rank_ic": allr(headline)["mean_rank_ic_h5"], "combo.ew.rank_ic": allr("EW")["mean_rank_ic_h5"],
               "combo.diff_vs_ew.t_nw": comp[cand]["t_nw_diff"], "combo.candidate": cand, "combo.fill_rate": fill, "combo.trial_ids": trial_ids,
               "combo.n_folds": folds.height, "combo.n_rows": summ.height}
    (out / "metrics.json").write_text(json.dumps(metrics, indent=1, default=str))
    return {"out": str(out), **metrics, "selection": sel}
