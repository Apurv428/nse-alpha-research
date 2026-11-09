"""Combiners (PRD section 7): equal-weight z, ridge (inner purged alpha search), LightGBM (L2, early stopping)."""
from __future__ import annotations

import numpy as np
import polars as pl
from scipy.stats import norm
from sklearn.linear_model import Ridge

ALPHAS = [0.1, 1.0, 10.0, 100.0, 1000.0]
LGBM_PARAMS = dict(objective="regression", num_leaves=15, min_data_in_leaf=2000, learning_rate=0.03, feature_fraction=0.8,
                   bagging_fraction=0.7, bagging_freq=1, lambda_l2=10.0, verbose=-1, seed=7, deterministic=True,
                   force_row_wise=True, num_threads=4)
LGBM_MAX_ROUNDS, LGBM_PATIENCE = 1000, 100


def gaussian_rank_target(df: pl.DataFrame, col: str = "fwd_ret") -> pl.Series:
    """y = Phi^-1((rank(R) - 0.5) / n) within each date."""
    r = df.select(((pl.col(col).rank().over("trade_date") - 0.5) / pl.len().over("trade_date")).alias("u"))["u"].to_numpy()
    return pl.Series("y", norm.ppf(r))


def ew_score(X: np.ndarray) -> np.ndarray:
    """Mean of the signed z_neu (signs are all + by pre-registration); re-standardized per date by the caller."""
    return X.mean(axis=1)


def fit_ridge(Xtr: np.ndarray, ytr: np.ndarray, Xin: np.ndarray, yin: np.ndarray, Xval: np.ndarray, yval: np.ndarray):
    """No intercept. alpha from ALPHAS by validation MSE on the inner purged split; refit on the full training window."""
    mse = {}
    for a in ALPHAS:
        m = Ridge(alpha=a, fit_intercept=False).fit(Xin, yin)
        mse[a] = float(np.mean((yval - m.predict(Xval)) ** 2))
    best = min(mse, key=mse.get)
    final = Ridge(alpha=best, fit_intercept=False).fit(Xtr, ytr)
    return final, {"alpha": best, "val_mse": mse, "coef": final.coef_.tolist()}


def fit_lgbm(Xtr, ytr, Xin, yin, Xval, yval, names: list[str]):
    import lightgbm as lgb

    d_in = lgb.Dataset(Xin, yin, feature_name=names, free_raw_data=False)
    d_val = lgb.Dataset(Xval, yval, reference=d_in, feature_name=names, free_raw_data=False)
    m0 = lgb.train(LGBM_PARAMS, d_in, num_boost_round=LGBM_MAX_ROUNDS, valid_sets=[d_val],
                   callbacks=[lgb.early_stopping(LGBM_PATIENCE, verbose=False)])
    best = max(1, int(m0.best_iteration or 1))
    final = lgb.train(LGBM_PARAMS, lgb.Dataset(Xtr, ytr, feature_name=names), num_boost_round=best)
    gain = dict(zip(names, final.feature_importance(importance_type="gain").tolist()))
    return final, {"best_iteration": best, "gain": gain}
