"""Statutory + broker cost model from config/costs.yaml (PRD section 8). Costs are per side, as INR."""
from __future__ import annotations

import datetime as dt
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
COMPONENTS = ["stt", "exchange", "sebi", "stamp", "brokerage", "gst", "dp"]


@lru_cache(maxsize=4)
def load_schedule(path: str | None = None) -> dict:
    p = Path(path) if path else ROOT / "config" / "costs.yaml"
    cfg = yaml.safe_load(p.read_text())
    for r in cfg["rows"]:
        r["valid_from"] = dt.date.fromisoformat(str(r["valid_from"]))
    return cfg


def rate(cfg: dict, component: str, segment: str, side: str, on: dt.date, brokerage_bp: float | None = None) -> float:
    """Latest dated row with valid_from <= `on` whose side matches (`both` matches any side)."""
    if component == "brokerage" and brokerage_bp is not None:
        # sensitivity: delivery uses the stated bp; futures scale in proportion to the base schedule (1/3 of delivery bp)
        return brokerage_bp / 1e4 if segment == "eq_delivery" else brokerage_bp / 1e4 / 3.0
    rows = [r for r in cfg["rows"] if r["component"] == component and r["segment"] == segment and r["side"] in (side, "both") and r["valid_from"] <= on]
    if not rows:
        return 0.0
    return max(rows, key=lambda r: r["valid_from"])["rate"]


def trade_cost(segment: str, side: str, notional_inr: float, on: dt.date, n_scrips: int = 1, cfg: dict | None = None,
               brokerage_bp: float | None = None) -> dict:
    """Cost of one trade side in INR, by component. `n_scrips` matters only for the fixed DP charge on delivery sells."""
    assert segment in ("eq_delivery", "stk_future") and side in ("buy", "sell")
    cfg = cfg or load_schedule()
    r = lambda c: rate(cfg, c, segment, side, on, brokerage_bp if c == "brokerage" else None)
    out = {c: r(c) * notional_inr for c in ("stt", "exchange", "sebi", "stamp", "brokerage")}
    out["gst"] = cfg["gst_rate"] * (out["brokerage"] + out["exchange"] + out["sebi"])
    out["dp"] = cfg["dp_charge_inr"] * n_scrips if (segment == "eq_delivery" and side == "sell" and notional_inr > 0) else 0.0
    out["total"] = sum(out[c] for c in COMPONENTS)
    return out
