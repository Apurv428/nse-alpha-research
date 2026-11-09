"""silver.security_master: permanent security id `sid` (PRD section 4, "Security master linking").

Pairs (isin, symbol) get a new sid at first appearance, then are linked when
  (b) the same ISIN reappears under a new symbol (rename), or
  (a) the same symbol reappears under a new ISIN with no overlapping trading and at most 5 sessions
      between the old last trade and the new first trade (ISIN change after split/bonus/demerger).
Rule (a) does not require a corporate-actions file (DECISIONS D-012); when one exists the link records
whether a split/bonus/demerger explains it. Every link is logged with its reason.
sid numbers are assigned by (first_date, symbol, isin) so they do not change when later data is added.
"""
from __future__ import annotations

import polars as pl

MAX_GAP_SESSIONS = 5


class _UF:
    def __init__(self, n):
        self.p = list(range(n))

    def find(self, x):
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[max(ra, rb)] = min(ra, rb)


def session_calendar(cm: pl.DataFrame) -> pl.DataFrame:
    """Dense session index over every date with at least one cash-market row."""
    return (cm.select("trade_date").unique().sort("trade_date")
            .with_row_index("sess").with_columns(pl.col("sess").cast(pl.Int64)))


def build_security_master(cm: pl.DataFrame, calendar: pl.DataFrame, ca: pl.DataFrame | None = None):
    """Returns (master, pair_map). master: one row per (isin, symbol) segment with its sid."""
    sess_of = dict(zip(calendar["trade_date"].to_list(), calendar["sess"].to_list()))
    pairs = (cm.with_columns(pl.col("isin").fill_null("").str.strip_chars())
             .with_columns(pl.when(pl.col("isin") == "").then(pl.lit("NOISIN:") + pl.col("symbol")).otherwise(pl.col("isin")).alias("isin"))
             .group_by("isin", "symbol").agg(first_date=pl.col("trade_date").min(), last_date=pl.col("trade_date").max(),
                                             n_rows=pl.len())
             .sort("first_date", "symbol", "isin"))
    rows = pairs.to_dicts()
    n = len(rows)
    uf = _UF(n)
    reason: dict[int, str] = {}
    by_isin: dict[str, list[int]] = {}
    by_sym: dict[str, list[int]] = {}
    for i, r in enumerate(rows):
        by_isin.setdefault(r["isin"], []).append(i)
        by_sym.setdefault(r["symbol"], []).append(i)
    for isin, idx in by_isin.items():  # rule (b): rename
        for j in idx[1:]:
            uf.union(idx[0], j)
            reason[j] = "rename_same_isin"
    ca_by_sym: dict[str, list] = {}
    if ca is not None and ca.height:
        for r in ca.filter(pl.col("action").is_in(["split", "bonus", "demerger"])).select("symbol", "ex_date").iter_rows():
            ca_by_sym.setdefault(r[0], []).append(r[1])
    for sym, idx in by_sym.items():  # rule (a): ISIN change, same symbol
        idx = sorted(idx, key=lambda i: rows[i]["first_date"])
        for a, b in zip(idx, idx[1:]):
            ra, rb = rows[a], rows[b]
            if ra["isin"] == rb["isin"] or rb["first_date"] <= ra["last_date"]:
                continue  # same ISIN handled above / overlapping trading: not the same listing
            gap = sess_of[rb["first_date"]] - sess_of[ra["last_date"]] - 1
            if gap <= MAX_GAP_SESSIONS:
                uf.union(a, b)
                has_ca = any(abs(sess_of.get(e, 10**9) - sess_of[rb["first_date"]]) <= MAX_GAP_SESSIONS or
                             ra["last_date"] <= e <= rb["first_date"] for e in ca_by_sym.get(sym, []))
                reason[b] = "isin_change_same_symbol" + ("+corp_action" if has_ca else "")
    # sid numbering by component's earliest (first_date, symbol, isin)
    comp_key: dict[int, tuple] = {}
    for i, r in enumerate(rows):
        k = uf.find(i)
        key = (r["first_date"], r["symbol"], r["isin"])
        if k not in comp_key or key < comp_key[k]:
            comp_key[k] = key
    order = sorted(comp_key, key=lambda k: comp_key[k])
    sid_of_comp = {k: s + 1 for s, k in enumerate(order)}
    master = pl.DataFrame({
        "sid": [sid_of_comp[uf.find(i)] for i in range(n)],
        "isin": [r["isin"] for r in rows], "symbol": [r["symbol"] for r in rows],
        "valid_from": [r["first_date"] for r in rows], "valid_to": [r["last_date"] for r in rows],
        "n_rows": [r["n_rows"] for r in rows],
        "link_reason": [reason.get(i, "new") for i in range(n)],
    }, schema_overrides={"sid": pl.Int64}).sort("sid", "valid_from")
    return master, master.select("isin", "symbol", "sid")


def attach_sid(cm: pl.DataFrame, pair_map: pl.DataFrame) -> pl.DataFrame:
    cm = cm.with_columns(pl.col("isin").fill_null("").str.strip_chars())
    cm = cm.with_columns(pl.when(pl.col("isin") == "").then(pl.lit("NOISIN:") + pl.col("symbol")).otherwise(pl.col("isin")).alias("isin"))
    return cm.join(pair_map, on=["isin", "symbol"], how="left")
