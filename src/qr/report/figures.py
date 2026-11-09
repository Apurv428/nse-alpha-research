"""`qr figures`: PDFs into report/figures/ from run artifacts. A figure whose input is missing is skipped (the report shows a placeholder box)."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import polars as pl

from qr.report.ledger import ROOT, _latest

OUT = ROOT / "report" / "figures"


def _save(fig, name: str) -> str:
    OUT.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(OUT / f"{name}.pdf")
    plt.close(fig)
    return name


def make_all(runs: Path = ROOT / "runs") -> list[str]:
    made = []
    ev, pf, oos = _latest(runs, "eval_*"), _latest(runs, "portfolios_*"), runs / "oos"
    if ev and (ev / "daily_ic_neu.parquet").exists():
        d = pl.read_parquet(ev / "daily_ic_neu.parquet").filter(pl.col("h") == 5).sort("trade_date")
        fig, ax = plt.subplots(figsize=(7, 3.5))
        for s in d["signal"].unique(maintain_order=True):
            g = d.filter(pl.col("signal") == s).drop_nulls("rank_ic")
            ax.plot(g["trade_date"].to_list(), np.cumsum(g["rank_ic"].to_numpy()), label=s, lw=1)
        ax.set_ylabel("cumulative daily rank IC (h=5, neutral)"); ax.legend(fontsize=6, ncol=2)
        made.append(_save(fig, "f2_cum_ic"))
    if ev and (ev / "decay.csv").exists():
        d = pl.read_csv(ev / "decay.csv")
        fig, ax = plt.subplots(figsize=(7, 3.5))
        hs = [c for c in d.columns if c not in ("signal", "version")]
        for r in d.iter_rows(named=True):
            ax.plot(hs, [r[h] for h in hs], marker="o", ms=3, lw=1, ls="-" if r["version"].startswith("neu") else "--", label=f"{r['signal']} ({r['version']})")
        ax.set_xlabel("horizon (sessions)"); ax.set_ylabel("mean rank IC"); ax.legend(fontsize=5, ncol=2)
        made.append(_save(fig, "f3_decay"))
    if ev and (ev / "corr_scores.csv").exists():
        c = pl.read_csv(ev / "corr_scores.csv")
        names = [x for x in c.columns if x not in ("signal", "version")]
        c = c.filter(pl.col("version") == c["version"][0]) if "version" in c.columns else c
        fig, ax = plt.subplots(figsize=(5, 4.5))
        im = ax.imshow(c.select(names).to_numpy(), vmin=-1, vmax=1, cmap="RdBu_r")
        ax.set_xticks(range(len(names)), names, rotation=90, fontsize=6); ax.set_yticks(range(len(names)), names, fontsize=6); fig.colorbar(im)
        made.append(_save(fig, "f4_corr"))
    for tag, d, name in (("dev", pf, "f5_cum_active_dev"), ("oos", oos, "f5_cum_active")):
        f = Path(d) / "p1_net_weekly_active.parquet" if d else None
        if f is not None and f.exists():
            w = pl.read_parquet(f).sort("date")
            fig, ax = plt.subplots(figsize=(7, 3.2))
            ax.plot(w["date"].to_list(), np.cumsum(w["ret"].to_numpy()), lw=1)
            ax.set_ylabel(f"cumulative net active return, P1 ({tag}, sum of weekly)")
            made.append(_save(fig, name))
    if pf and (pf / "capacity_p1.csv").exists():
        g = pl.read_csv(pf / "capacity_p1.csv")
        fig, ax = plt.subplots(figsize=(5.5, 3.2))
        ax.semilogx(g["aum_cr"].to_numpy(), g["metric"].to_numpy(), marker="o")
        ax.set_xlabel("AUM (Rs crore)"); ax.set_ylabel("P1 net IR")
        made.append(_save(fig, "f6_capacity"))
    return made
