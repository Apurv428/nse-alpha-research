import math

import numpy as np
import pytest
import statsmodels.api as sm
from scipy.stats import norm

from qr.stats import bootstrap as bs
from qr.stats import dsr as D
from qr.stats.newey_west import nw_lag, nw_tstat, plain_t


def ar1(n, phi, seed=0):
    rng = np.random.default_rng(seed)
    x = np.zeros(n)
    e = rng.normal(size=n)
    for t in range(1, n):
        x[t] = phi * x[t - 1] + e[t]
    return x + 0.1


@pytest.mark.parametrize("phi,h", [(0.0, 1), (0.6, 1), (0.8, 5), (0.5, 21)])
def test_nw_matches_statsmodels_on_ar1(phi, h):
    x = ar1(1500, phi)
    L = nw_lag(len(x), h)
    mine = nw_tstat(x, h)
    res = sm.OLS(x, np.ones_like(x)).fit(cov_type="HAC", cov_kwds={"maxlags": L})
    assert mine["lags"] == L
    assert mine["t_nw"] == pytest.approx(float(res.tvalues[0]), rel=1e-6)


def test_nw_lag_formula():
    assert nw_lag(2900, 1) == int(math.floor(4 * (2900 / 100) ** (2 / 9)))
    assert nw_lag(2900, 21) == 20
    assert nw_lag(100, 5) == max(4, 4)


def test_nw_agrees_in_sign_with_nonoverlapping_t_and_is_smaller_than_plain_under_autocorr():
    x = ar1(3000, 0.9, seed=3)
    assert abs(nw_tstat(x, 1)["t_nw"]) < abs(plain_t(x))  # positive autocorrelation inflates plain t
    nonover = x[::10]
    assert np.sign(nw_tstat(x, 10)["t_nw"]) == np.sign(plain_t(nonover))


def test_psr_reproduces_published_example_hedge_fund():
    # Lopez de Prado, "The Sharpe Ratio Efficient Frontier" slides: 24 monthly returns,
    # SR = 0.458, skew = -2.448, kurt = 10.164 -> PSR(0) = 0.913 (non-normal), 0.982 (normal)
    assert D.psr(0.458, 24, -2.448, 10.164) == pytest.approx(0.913, abs=5e-4)
    assert D.psr(0.458, 24, 0.0, 3.0) == pytest.approx(0.982, abs=5e-4)
    assert D.psr(0.458, 36, -2.448, 10.164) == pytest.approx(0.953, abs=1e-3)  # three-year record


def test_dsr_with_one_trial_equals_psr_zero():
    out = D.dsr(0.2, 400, -0.3, 4.0, 0.01, 1)
    assert out["sr_star"] == 0.0 and out["dsr"] == pytest.approx(D.psr(0.2, 400, -0.3, 4.0, 0.0))


def test_expected_max_sr_matches_monte_carlo_of_max_of_n_normals():
    rng = np.random.default_rng(7)
    N, sd = 50, 0.1
    mc = rng.normal(0, sd, (20000, N)).max(axis=1).mean()
    assert D.expected_max_sr(sd * sd, N) == pytest.approx(mc, rel=0.05)


def test_dsr_of_best_of_50_noise_strategies_is_well_below_095():
    rng = np.random.default_rng(11)
    T, N = 400, 50
    R = rng.normal(0, 0.02, (N, T))
    srs = R.mean(1) / R.std(1, ddof=1)
    k = int(srs.argmax())
    from scipy.stats import kurtosis, skew
    out = D.dsr(srs[k], T, float(skew(R[k])), float(kurtosis(R[k], fisher=False)), float(np.var(srs, ddof=1)), N)
    assert out["dsr"] < 0.95
    assert D.psr(srs[k], T, 0.0, 3.0, 0.0) > out["dsr"]  # deflation lowers the probability


def test_n_eff_clusters_correlated_trials():
    rng = np.random.default_rng(2)
    base = rng.normal(size=(2, 300))
    R = np.vstack([base[0], base[0] + 0.05 * rng.normal(size=300), base[1], base[1] + 0.05 * rng.normal(size=300), rng.normal(size=300)])
    assert D.n_eff(R, 0.7) == 3


def test_stationary_bootstrap_ci_covers_mean_and_is_seeded():
    x = ar1(400, 0.3, seed=5)
    a = bs.bootstrap_ci(x, bs.stat_mean, mean_block=4, B=2000, seed=1)
    b = bs.bootstrap_ci(x, bs.stat_mean, mean_block=4, B=2000, seed=1)
    assert a == b
    assert a["ci_lo"] < x.mean() < a["ci_hi"]
    idx = bs.sb_indices(400, 4, 50, 3)
    assert idx.min() >= 0 and idx.max() < 400
    # mean block length ~ 4: share of continuing steps ~ 1 - 1/4
    cont = ((idx[:, 1:] - idx[:, :-1]) % 400 == 1).mean()
    assert cont == pytest.approx(0.75, abs=0.03)
