"""Backtest engine on a hand-built panel: accounting identities, timing, caps, costs, determinism."""
import datetime as dt

import numpy as np
import pytest

from qr.portfolio.backtest import MISS_MAX, Panel, simulate

START = dt.date(2025, 1, 6)


def mk(T=60, N=20, seed=0, drift=None, adv=1e9):
    rng = np.random.default_rng(seed)
    dates, d = [], START
    while len(dates) < T:
        if d.weekday() < 5:
            dates.append(d)
        d += dt.timedelta(days=1)
    ret = rng.normal(0, 0.01, (T, N))
    if drift is not None:
        ret = ret + drift[None, :]
    ret[0] = np.nan
    P = Panel(dates, 0, np.arange(N), ret, np.full((T, N), adv), np.full((T, N), 0.02), np.full((T, N), 3e-4),
              rng.normal(0, 0.01, (T, N)), np.zeros((T, N), bool), np.full(T, 0.0005))
    for i in range(T):
        P.univ[dates[i]] = (np.ones(N, bool), np.ones(N, bool))
    return P


def weekly_scores(P, vec):
    return {P.dates[i]: vec.copy() for i in range(4, len(P.dates) - 1, 5)}


def test_zero_cost_single_name_tracks_stock_return():
    P = mk(N=1, drift=np.array([0.0]))
    sc = {P.dates[4]: np.array([1.0])}
    out = simulate(P, sc, "P1", cost_mult=0.0, rf_annual=0.0, enter=1.0, keep=1.0)
    d = out["daily"]
    fill = P.dates[5]
    px = np.cumprod(1 + np.nan_to_num(P.ret[:, 0]))
    nav = d.filter(d["date"] >= fill)["nav"].to_numpy()
    assert nav / nav[0] == pytest.approx(px[5:] / px[5], rel=1e-9)   # earns returns only after the fill close


def test_gross_not_below_net_and_costs_positive_and_reconcile():
    drift = np.linspace(-0.002, 0.002, 20)
    P = mk(T=120, drift=drift)
    sc = weekly_scores(P, drift)
    g = simulate(P, sc, "P1", cost_mult=0.0, rf_annual=0.0)
    n = simulate(P, sc, "P1", cost_mult=1.0, rf_annual=0.0)
    assert g["daily"]["nav"][-1] > n["daily"]["nav"][-1]
    assert sum(g["components_inr"].values()) == 0.0
    assert sum(n["components_inr"].values()) > 0
    # NAV gap between gross and net is at least the INR costs paid (compounded on top)
    gap = g["daily"]["nav"][-1] - n["daily"]["nav"][-1]
    assert gap >= 0.9 * sum(n["components_inr"].values())
    assert n["turnover_oneway_pa"] > 0


def test_planted_score_makes_money_and_shuffled_score_does_not():
    drift = np.linspace(-0.003, 0.003, 20)
    P = mk(T=200, drift=drift, seed=3)
    good = simulate(P, weekly_scores(P, drift), "P1", cost_mult=0.0, rf_annual=0.0)["daily"]["nav"]
    rng = np.random.default_rng(1)
    bad = simulate(P, {d: rng.permutation(drift) for d in weekly_scores(P, drift)}, "P1", cost_mult=0.0, rf_annual=0.0)["daily"]["nav"]
    assert good[-1] / good[0] > 1.1 and good[-1] > bad[-1]


def test_participation_cap_limits_trades_and_is_reported():
    P = mk(T=60, adv=2e6)           # ADV Rs 20 lakh: a 10% cap is Rs 2 lakh per name
    sc = weekly_scores(P, np.arange(20.0))
    out = simulate(P, sc, "P1", aum_cr=10.0, cost_mult=0.0, rf_annual=0.0)
    assert out["cap_unfilled_share"] > 0.5
    assert out["daily"]["long_val"].max() <= 20 * 2e5 * 1.5 + 1       # never more than cap-per-name (plus a little drift)


def test_p2_short_leg_gains_when_shorted_futures_fall_and_dollar_neutral():
    N = 20
    P = mk(T=120, N=N, seed=5)
    P.ret = np.where(np.isnan(P.ret), np.nan, P.ret * 0.0)         # stocks flat
    fr = np.zeros(P.ret.shape); fr[:, :4] = -0.004; fr[:, 16:] = 0.0 # bottom-scored names' futures fall
    P.fret = fr
    sc = weekly_scores(P, np.arange(N, dtype=float))               # high index = high score; bottom = low index
    out = simulate(P, sc, "P2", cost_mult=0.0, rf_annual=0.0)
    d = out["daily"].drop_nulls("ret")
    assert d["nav"][-1] > d["nav"][0]
    row = out["daily"].filter(out["daily"]["short_val"] > 0)[5]
    assert row["short_val"][0] == pytest.approx(row["long_val"][0], rel=0.15)   # ~dollar-neutral between rebalances


def test_deterministic_and_delisting_writeoff():
    P = mk(T=80, N=5, seed=2)
    sc = weekly_scores(P, np.array([5.0, 4, 3, 2, 1]))
    a = simulate(P, sc, "P1", enter=1.0, keep=1.0)["daily"]["nav"].to_numpy()
    b = simulate(P, sc, "P1", enter=1.0, keep=1.0)["daily"]["nav"].to_numpy()
    assert (a == b).all()
    P.ret[10:, 0] = np.nan                                           # name 0 stops trading at session 10
    hc0 = simulate(P, sc, "P1", enter=1.0, keep=1.0, haircut=0.0, cost_mult=0.0, rf_annual=0.0)["daily"]["nav"].to_numpy()
    hc3 = simulate(P, sc, "P1", enter=1.0, keep=1.0, haircut=0.3, cost_mult=0.0, rf_annual=0.0)["daily"]["nav"].to_numpy()
    assert hc3[-1] < hc0[-1] and MISS_MAX == 10


def test_metrics_and_capacity_on_synthetic_panel():
    from qr.portfolio.capacity import AUM_GRID_CR, break_even_multiple, capacity_from_grid, capacity_grid
    from qr.portfolio.metrics import summarize
    drift = np.linspace(-0.002, 0.002, 20)
    P = mk(T=200, drift=drift, seed=7, adv=5e6)
    sc = weekly_scores(P, drift)
    g = capacity_grid(P, sc, "P1")
    assert g["aum_cr"].to_list() == AUM_GRID_CR and g["cap_unfilled_share"][-1] >= g["cap_unfilled_share"][0]
    c = capacity_from_grid(g)
    assert set(c) == {"half_metric_aum_cr", "cap_binding_aum_cr", "capacity_aum_cr", "grid_max_cr"}
    be = break_even_multiple(P, sc, "P1")
    assert be is None or be > 0
    o = simulate(P, sc, "P1")
    m = summarize(o["daily"], np.array([P.bench_ret[0]] * 0 + [0.0005] * (o["daily"].height - 1)))
    assert {"cagr", "vol", "sharpe", "max_drawdown", "worst_month", "weekly_hit_rate", "ir", "beta", "tracking_error"} <= set(m)
