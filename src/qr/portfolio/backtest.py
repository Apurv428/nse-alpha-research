"""Daily-marked weekly-rebalanced backtests for P1 (long-only vs Nifty 500 TRI) and P2 (long cash / short futures).

Timing: the signal is the score at the week's last close t; the trade fills at the NEXT close t+1; the book earns
returns from t+2. Everything a rebalance uses (universe membership, ADV, sigma, half-spread, scores) is dated <= t.
Costs: statutory (config/costs.yaml, dated), half-spread and square-root impact, charged in INR at the fill.
Participation cap: a trade is limited to `cap_adv` x ADV; the remainder is simply not done (next rebalance retries).
Missing prices: a held name with no price carries flat for up to MISS_MAX sessions, then is written off at (1 - haircut).
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

import numpy as np
import polars as pl

from qr.portfolio import construct as C
from qr.portfolio.costs import load_schedule, trade_cost
from qr.portfolio.impact import cost_inputs, impact_fraction

MISS_MAX = 10
CR = 1e7
COMPONENTS = ["stt", "exchange", "stamp", "brokerage_gst", "dp", "spread", "impact", "roll"]


@dataclass
class Panel:
    dates: list                     # trade_date per row index
    sess0: int
    sids: np.ndarray
    ret: np.ndarray                 # [T, N] total-return daily, nan = no row
    adv: np.ndarray
    sigma: np.ndarray
    hs: np.ndarray                  # half spread
    fret: np.ndarray                # futures daily return of the held near-month contract
    froll: np.ndarray               # bool
    bench_ret: np.ndarray           # [T]
    univ: dict = field(default_factory=dict)   # rebalance row index -> (in_univ[N], in_fno[N])


def _dense(df: pl.DataFrame, col: str, sid_ix: dict, sess0: int, T: int, N: int, fill=np.nan, dtype=float) -> np.ndarray:
    out = np.full((T, N), fill, dtype=dtype)
    d = df.filter(pl.col(col).is_not_null() if dtype is float else pl.lit(True))
    r = (d["sess"].to_numpy() - sess0)
    c = np.array([sid_ix.get(s, -1) for s in d["sid"].to_list()])
    m = (c >= 0) & (r >= 0) & (r < T)
    out[r[m], c[m]] = d[col].to_numpy()[m]
    return out


def build_panel(prices, calendar, bench, universe, fut, ci=None) -> Panel:
    """All inputs come from the clipped qr.panel.io loaders. `ci` = cost_inputs output (computed if None)."""
    ci = cost_inputs(prices, calendar) if ci is None else ci
    cal = calendar.sort("sess")
    sess0, T = int(cal["sess"].min()), cal.height
    ever = universe.filter(pl.col("in_univ"))["sid"].unique().sort()
    sid_ix = {s: i for i, s in enumerate(ever.to_list())}
    N = len(sid_ix)
    p = prices.select("sid", "sess", "ret_1d")
    ret = _dense(p, "ret_1d", sid_ix, sess0, T, N)
    adv, sig, hs = (_dense(ci, c, sid_ix, sess0, T, N) for c in ("adv", "sigma", "half_spread"))
    if fut.height and "sess" not in fut.columns:                       # silver.fut_cont is keyed by trade_date
        fut = fut.join(cal.select("trade_date", "sess"), on="trade_date")
    fret = _dense(fut, "ret_1d_fut", sid_ix, sess0, T, N)
    froll = _dense(fut.with_columns(pl.col("roll_flag").cast(pl.Float64)), "roll_flag", sid_ix, sess0, T, N, fill=0.0) > 0.5
    b = cal.join(bench.select("trade_date", "n500_tri"), on="trade_date", how="left").sort("sess")
    tri = b["n500_tri"].to_numpy().astype(float)
    bret = np.concatenate([[np.nan], tri[1:] / tri[:-1] - 1.0])
    return Panel(cal["trade_date"].to_list(), sess0, ever.to_numpy(), ret, adv, sig, hs, fret, froll, bret)


def attach_universe(panel: Panel, universe: pl.DataFrame, rebal_dates: list) -> None:
    """PIT membership for each rebalance signal date: the latest month_start <= that date."""
    u = universe.sort("month_start")
    ms = u["month_start"].unique().sort().to_list()
    sid_ix = {s: i for i, s in enumerate(panel.sids.tolist())}
    by_month = {}
    for m in ms:
        g = u.filter(pl.col("month_start") == m)
        iu, ifo = np.zeros(len(sid_ix), bool), np.zeros(len(sid_ix), bool)
        for s, a, b in zip(g["sid"].to_list(), g["in_univ"].to_list(), g["in_fno"].to_list()):
            k = sid_ix.get(s)
            if k is not None:
                iu[k], ifo[k] = bool(a), bool(b)
        by_month[m] = (iu, ifo)
    for d in rebal_dates:
        cand = [m for m in ms if m <= d]
        if cand:
            panel.univ[d] = by_month[cand[-1]]


def _stat_rates(segment: str, side: str, on: dt.date, brokerage_bp, cm: float) -> dict:
    t = trade_cost(segment, side, CR, on, n_scrips=1, brokerage_bp=brokerage_bp)
    return {"stt": t["stt"] / CR * cm, "exchange": t["exchange"] / CR * cm, "stamp": t["stamp"] / CR * cm,
            "brokerage_gst": (t["brokerage"] + t["gst"]) / CR * cm, "sebi": t["sebi"] / CR * cm,
            "dp": t["dp"] * cm}  # dp is a fixed INR amount per scrip (cm applied to it too)


def simulate(panel: Panel, scores: dict, book: str, aum_cr: float = 1.0, cost_mult: float = 1.0, Y: float = 1.0,
             brokerage_bp=None, haircut: float = 0.0, rf_annual: float = 0.065, cap_adv: float = 0.10,
             enter: float = 0.10, keep: float = 0.20, margin: float = 0.20, first_date=None, last_date=None) -> dict:
    """scores: {signal_date: float array over panel.sids}. book in {"P1", "P2"}. cost_mult=0 gives the gross run."""
    assert book in ("P1", "P2")
    seg_idx = {d: i for i, d in enumerate(panel.dates)}
    T, N = panel.ret.shape
    sig_dates = sorted(d for d in scores if d in seg_idx and d in panel.univ)
    if first_date:
        sig_dates = [d for d in sig_dates if d >= first_date]
    fill_at = {seg_idx[d] + 1: d for d in sig_dates if seg_idx[d] + 1 < T}
    s_start = min(fill_at)
    s_end = (seg_idx[last_date] if last_date else T - 1)
    V, S = np.zeros(N), np.zeros(N)
    cash, miss = aum_cr * CR, np.zeros(N, int)
    comp = dict.fromkeys(COMPONENTS, 0.0)
    rows, rebs = [], []
    rf_d = rf_annual / 252.0
    for s in range(s_start, s_end + 1):
        r, fr = panel.ret[s], panel.fret[s]
        # --- mark to market (returns realised on s accrue to positions held from the previous close) ---
        held = V > 0
        pres = np.isfinite(r)
        V = np.where(held & pres, V * (1 + np.nan_to_num(r)), V)
        miss = np.where(held & ~pres, miss + 1, 0)
        wo = held & (miss > MISS_MAX)
        if wo.any():
            cash += float((V[wo] * (1 - haircut)).sum()); V[wo] = 0.0; miss[wo] = 0
        if book == "P2":
            sh = S > 0
            fp = np.isfinite(fr)
            cash += float(-(S[sh & fp] * fr[sh & fp]).sum())
            S = np.where(sh & fp, S * (1 + np.nan_to_num(fr)), S)
            rl = sh & panel.froll[s]
            if rl.any() and cost_mult > 0:
                d = panel.dates[s]
                rb, rs = _stat_rates("stk_future", "buy", d, brokerage_bp, cost_mult), _stat_rates("stk_future", "sell", d, brokerage_bp, cost_mult)
                stat = sum(rb[k] + rs[k] for k in ("stt", "exchange", "stamp", "brokerage_gst", "sebi"))
                sp = 2 * np.nan_to_num(panel.hs[s - 1][rl]) * cost_mult
                cost = float(S[rl].sum() * stat + (S[rl] * sp).sum())
                comp["roll"] += cost; cash -= cost
        cash += max(cash, 0.0) * rf_d
        # --- rebalance at this fill session ---
        if s in fill_at:
            t = fill_at[s]; ti = seg_idx[t]
            nav = V.sum() + cash
            iu, ifo = panel.univ[t]
            tradable = np.isfinite(r) & np.isfinite(panel.adv[ti]) & (panel.adv[ti] > 0)
            elig = iu & tradable & (ifo if book == "P2" else True)
            sc = scores[t]
            d = panel.dates[s]
            if book == "P1":
                tgt = C.select_p1(sc, elig, V > 0, enter, keep)
                n = max(int(tgt.sum()), 1)
                want_long = np.where(tgt, nav / n, 0.0)
                want_short = np.zeros(N)
            else:
                lg, sh_ = C.select_p2(sc, elig)
                lng = nav / (1 + margin)
                want_long = np.where(lg, lng / max(int(lg.sum()), 1), 0.0)
                want_short = np.where(sh_, lng / max(int(sh_.sum()), 1), 0.0)
            tot_desired = tot_done = 0.0
            for leg, cur, want, seg in (("L", V, want_long, "eq_delivery"), ("S", S, want_short, "stk_future")):
                if leg == "S" and book != "P2":
                    continue
                tr_ok = tradable if leg == "L" else (tradable & np.isfinite(fr))
                delta = np.where(tr_ok, want - cur, 0.0)
                cap = cap_adv * np.nan_to_num(panel.adv[ti])
                done = np.clip(delta, -cap, cap)
                tot_desired += float(np.abs(delta).sum()); tot_done += float(np.abs(done).sum())
                # for the long leg 'buy' adds cash outflow; for the short leg selling futures adds short notional
                buy_side = "buy" if leg == "L" else "sell"      # side of the trade that INCREASES the position
                dec_side = "sell" if leg == "L" else "buy"
                for side, mask in ((dec_side, done < 0), (buy_side, done > 0)):
                    if not mask.any():
                        continue
                    q = np.abs(done[mask])
                    rate = _stat_rates(seg, side, d, brokerage_bp, cost_mult)
                    stat = sum(rate[k] for k in ("stt", "exchange", "stamp", "brokerage_gst", "sebi"))
                    sp = np.nan_to_num(panel.hs[ti][mask]) * cost_mult
                    im = impact_fraction(panel.sigma[ti][mask], q, panel.adv[ti][mask], Y) * cost_mult
                    cost = q * (stat + sp + im)
                    dpc = rate["dp"] * mask.sum() if (seg == "eq_delivery" and side == "sell") else 0.0
                    # long buys / short covers consume cash; long sells / short entries free it (short margin stays in cash)
                    if leg == "L":
                        flow = -q.sum() if side == "buy" else q.sum()
                    else:
                        flow = 0.0
                    if leg == "L" and side == "buy":     # scale buys to the cash available (costs included)
                        avail = max(cash - 0.0, 0.0)
                        need = q.sum() + cost.sum()
                        k = min(1.0, avail / need) if need > 0 else 1.0
                        q, cost = q * k, cost * k; done[mask] = q; flow = -q.sum()
                    cash += flow - cost.sum() - dpc
                    cur[mask] += q if side == buy_side else -q
                    comp["stt"] += float(q.sum() * rate["stt"]); comp["exchange"] += float(q.sum() * (rate["exchange"] + rate["sebi"]))
                    comp["stamp"] += float(q.sum() * rate["stamp"]); comp["brokerage_gst"] += float(q.sum() * rate["brokerage_gst"])
                    comp["dp"] += dpc; comp["spread"] += float((q * sp).sum()); comp["impact"] += float((q * im).sum())
                    rebs.append((d, leg, side, float(q.sum())))
            rebs.append((d, "cap", "", tot_desired - tot_done))
            rebs.append((d, "des", "", tot_desired))
        nav_s = float(V.sum() + cash)
        rows.append((panel.dates[s], nav_s, int((V > 0).sum()), int((S > 0).sum()), float(V.sum()), float(S.sum())))
    daily = pl.DataFrame(rows, schema=["date", "nav", "n_long", "n_short", "long_val", "short_val"], orient="row")
    daily = daily.with_columns((pl.col("nav") / pl.col("nav").shift(1) - 1).alias("ret"))
    traded = sum(x[3] for x in rebs if x[1] in ("L", "S"))
    cap_gap = sum(x[3] for x in rebs if x[1] == "cap")
    des = sum(x[3] for x in rebs if x[1] == "des")
    years = max((daily["date"].max() - daily["date"].min()).days / 365.25, 1e-9)
    avg_nav = float(daily["nav"].mean())
    return {"daily": daily, "components_inr": comp, "avg_nav": avg_nav, "years": years,
            "turnover_oneway_pa": traded / 2.0 / avg_nav / years,
            "cap_unfilled_share": (cap_gap / des) if des > 0 else 0.0,
            "drag_bp_pa": {k: v / avg_nav / years * 1e4 for k, v in comp.items()}}
