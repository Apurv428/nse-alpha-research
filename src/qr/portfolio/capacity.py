"""AUM grid, capacity and break-even cost multiple (PRD section 8)."""
from __future__ import annotations

import numpy as np
import polars as pl

from qr.portfolio.backtest import simulate
from qr.portfolio.metrics import summarize

AUM_GRID_CR = [1, 10, 50, 100, 250, 500, 1000]


def _stat(book: str, out: dict, panel, rf: float) -> dict:
    d = out["daily"]
    dates = d["date"].to_list()
    ix = {x: i for i, x in enumerate(panel.dates)}
    b = np.array([panel.bench_ret[ix[x]] for x in dates])[1:]
    return summarize(d, b if book == "P1" else None, rf)


def headline_metric(book: str, m: dict) -> float:
    return m["ir"] if book == "P1" else m["sharpe"]


def capacity_grid(panel, scores: dict, book: str, rf_annual: float = 0.065, **kw) -> pl.DataFrame:
    rows = []
    for a in AUM_GRID_CR:
        o = simulate(panel, scores, book, aum_cr=a, rf_annual=rf_annual, **kw)
        m = _stat(book, o, panel, rf_annual)
        rows.append({"aum_cr": a, "metric": headline_metric(book, m), "cagr": m["cagr"], "cap_unfilled_share": o["cap_unfilled_share"],
                     "turnover_oneway_pa": o["turnover_oneway_pa"], **{f"drag_{k}": v for k, v in o["drag_bp_pa"].items()}})
    return pl.DataFrame(rows)


def capacity_from_grid(g: pl.DataFrame) -> dict:
    """Capacity = smaller of (a) the AUM where the metric first falls to half its Rs 1 crore value and
    (b) the AUM where more than 20% of desired trade value hits the ADV cap. None = not reached within the grid."""
    base = g["metric"][0]
    a = g.filter(pl.col("metric") <= 0.5 * base)["aum_cr"]
    b = g.filter(pl.col("cap_unfilled_share") > 0.20)["aum_cr"]
    ca, cb = (a[0] if a.len() else None), (b[0] if b.len() else None)
    c = [x for x in (ca, cb) if x is not None]
    return {"half_metric_aum_cr": ca, "cap_binding_aum_cr": cb, "capacity_aum_cr": min(c) if c else None, "grid_max_cr": int(g["aum_cr"].max())}


def break_even_multiple(panel, scores: dict, book: str, aum_cr: float = 1.0, rf_annual: float = 0.065, **kw) -> float | None:
    """Factor on total costs at which the net active return (P1) / excess CAGR over rf (P2) reaches 0, by bisection."""
    def ar(cm):
        o = simulate(panel, scores, book, aum_cr=aum_cr, cost_mult=cm, rf_annual=rf_annual, **kw)
        m = _stat(book, o, panel, rf_annual)
        return m["active_return"] if book == "P1" else m["cagr"] - rf_annual
    if ar(0.0) <= 0:
        return 0.0
    lo, hi = 1.0, 1.0
    if ar(1.0) <= 0:
        hi = 1.0; lo = 0.0
    else:
        while ar(hi) > 0 and hi < 64:
            lo, hi = hi, hi * 2
        if ar(hi) > 0:
            return None
    for _ in range(18):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if ar(mid) > 0 else (lo, mid)
    return (lo + hi) / 2
