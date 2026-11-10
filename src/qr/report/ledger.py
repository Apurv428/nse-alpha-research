"""`qr ledger`: RESULTS.md and report/numbers.tex, generated from run artifacts only (non-negotiable 4).

Every row names its source file and key. A number whose file or key does not exist prints "not run". Nothing here is typed by hand;
the report and README may only show results through `\\R{id}` (report) or the generated README block.
"""
from __future__ import annotations

import csv
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
NOT_RUN = "not run"


def _latest(runs: Path, pattern: str) -> Path | None:
    c = sorted(Path(runs).glob(pattern))
    return c[-1] if c else None


def _json(p: Path):
    return json.loads(p.read_text()) if p and p.exists() else None


def _dig(obj, path):
    for k in path:
        if obj is None:
            return None
        obj = obj.get(k) if isinstance(obj, dict) else None
    return obj


def _costs(p: Path, book: str, what: str):
    if not p or not p.exists():
        return None
    rows = list(csv.DictReader(p.open()))
    r = next((x for x in rows if x["book"] == book), None)
    if r is None:
        return None
    comp = {k: float(v) for k, v in r.items() if k.startswith("drag_bp_pa_")}
    tot = sum(comp.values())
    if what == "total":
        return tot
    return 100.0 * comp[f"drag_bp_pa_{what}"] / tot if tot and f"drag_bp_pa_{what}" in comp else None


def _sens(p: Path, book: str, case: str, col: str):
    return _cell(p, ("book", book), ("case", case), col=col)


def _cell(p: Path, *where, col: str):
    """One numeric cell of a CSV, picked by (column, value) filters."""
    if not p or not p.exists():
        return None
    r = next((x for x in csv.DictReader(p.open()) if all(x.get(k) == v for k, v in where)), None)
    return float(r[col]) if r and r.get(col) not in (None, "") else None


# (id, description, window, kind, dir pattern, file, key path / extra)
DEV = "2017-01-02 -> 2024-10-31"
REG = [
    ("data.n_sessions", "NSE sessions in the panel", "2012-2026", "json", "data_qa", "gate_report.json", ("n_sessions",)),
    ("data.n_sids", "Securities in the master", "2012-2026", "json", "data_qa", "gate_report.json", ("n_sids",)),
    ("data.n_delisted_in_univ", "Later-delisted names that were in the universe", "2012-2026", "json", "data_qa", "gate_report.json", ("n_delisted_in_univ",)),
    ("sig.best_neu.name", "Strongest neutralized signal (h=5)", "2013-2024", "json", "eval_*", "metrics.json", ("sig.best_neu.name",)),
    ("sig.best_neu.rank_ic_h5", "Its mean rank IC (h=5)", "2013-2024", "json", "eval_*", "metrics.json", ("sig.best_neu.rank_ic_h5",)),
    ("sig.best_neu.t_nw_h5", "Its Newey-West t (h=5)", "2013-2024", "json", "eval_*", "metrics.json", ("sig.best_neu.t_nw_h5",)),
    ("sig.n_pass_holm_t3", "Signal tests passing Holm and t>=3", "2013-2024", "json", "eval_*", "metrics.json", ("sig.n_pass_holm_t3",)),
    ("sig.max_rank_ic_h5", "Largest mean rank IC of any signal (h=5)", "2013-2024", "json", "eval_*", "metrics.json", ("sig.max_rank_ic_h5",)),
    ("combo.headline", "Headline combiner chosen by the pre-registered rule", DEV, "json", "combo_*", "metrics.json", ("combo.headline",)),
    ("combo.headline.rank_ic", "Headline combiner mean rank IC (h=5, walk-forward)", DEV, "json", "combo_*", "metrics.json", ("combo.headline.rank_ic",)),
    ("combo.ew.rank_ic", "Equal-weight mean rank IC (h=5, walk-forward)", DEV, "json", "combo_*", "metrics.json", ("combo.ew.rank_ic",)),
    ("combo.diff_vs_ew.t_nw", "Candidate minus EW, Newey-West t", DEV, "json", "combo_*", "metrics.json", ("combo.diff_vs_ew.t_nw",)),
]
for book, main in (("p1", "ir"), ("p2", "sharpe")):
    for tag, win, d in (("dev", DEV, "portfolios_*"), ("oos", "2024-11-01 -> 2026-10-30", "oos")):
        base = ("json", d, "metrics.json")
        REG += [
            (f"{book}.{tag}.{main}_net", f"{book.upper()} net {'IR vs Nifty 500 (price index)' if book == 'p1' else 'Sharpe on capital'}", win, *base, (f"{book}.{tag}.{main}_net",)),
            (f"{book}.{tag}.{main}_gross", f"{book.upper()} gross {'IR' if book == 'p1' else 'Sharpe'}", win, *base, (f"{book}.{tag}.{main}_gross",)),
            (f"{book}.{tag}.cagr_net", f"{book.upper()} net CAGR", win, *base, (f"{book}.{tag}.cagr_net",)),
            (f"{book}.{tag}.cagr_gross", f"{book.upper()} gross CAGR", win, *base, (f"{book}.{tag}.cagr_gross",)),
            (f"{book}.{tag}.vol_net", f"{book.upper()} net volatility (annualized)", win, *base, (f"{book}.{tag}.vol_net",)),
            (f"{book}.{tag}.avg_holdings_long_net", f"{book.upper()} average long holdings", win, *base, (f"{book}.{tag}.avg_holdings_long_net",)),
            (f"{book}.{tag}.max_drawdown_net", f"{book.upper()} net max drawdown", win, *base, (f"{book}.{tag}.max_drawdown_net",)),
            (f"{book}.{tag}.turnover_oneway_pa", f"{book.upper()} one-way turnover per year", win, *base, (f"{book}.{tag}.turnover_oneway_pa",)),
            (f"{book}.{tag}.cap_unfilled_share", f"{book.upper()} share of desired trades blocked by the 10% ADV cap (Rs 1 crore)", win, *base, (f"{book}.{tag}.cap_unfilled_share",)),
            (f"{book}.{tag}.psr0", f"{book.upper()} PSR(0)", win, *base, (f"{book}.{tag}.psr0",)),
            (f"{book}.{tag}.cost_drag_bp", f"{book.upper()} total cost drag, bp per year", win, "costs", d, "costs.csv", (book.upper(), "total")),
            (f"{book}.{tag}.stt_share_pct", f"{book.upper()} STT share of cost drag, %", win, "costs", d, "costs.csv", (book.upper(), "stt")),
            (f"{book}.{tag}.spread_share_pct", f"{book.upper()} spread share of cost drag, %", win, "costs", d, "costs.csv", (book.upper(), "spread")),
            (f"{book}.{tag}.impact_share_pct", f"{book.upper()} impact share of cost drag, %", win, "costs", d, "costs.csv", (book.upper(), "impact")),
        ]
        if book == "p1":
            for case, lab in (("brokerage_0bp", "brokerage 0 bp"), ("Y_0.5", "impact Y = 0.5"), ("Y_2.0", "impact Y = 2"), ("haircut_30pct", "30% delisting haircut"), ("cost_x2", "all costs doubled")):
                REG.append((f"p1.{tag}.sens.{case}", f"P1 net IR, sensitivity: {lab}", win, "sens", d, "sensitivities_p1.csv", ("P1", case, "metric")))
        if book == "p1":
            REG += [(f"p1.{tag}.bench_cagr", "Nifty 500 price index CAGR", win, *base, (f"p1.{tag}.bench_cagr_net",)),
                    (f"p1.{tag}.active_return_net", "P1 net active return vs benchmark (annualized)", win, *base, (f"p1.{tag}.active_return_net",)),
                    (f"p1.{tag}.active_return_gross", "P1 gross active return vs benchmark (annualized)", win, *base, (f"p1.{tag}.active_return_gross",)),
                    (f"p1.{tag}.tracking_error_net", "P1 net tracking error", win, *base, (f"p1.{tag}.tracking_error_net",)),
                    (f"p1.{tag}.beta_net", "P1 net beta to benchmark", win, *base, (f"p1.{tag}.beta_net",))]
    REG += [(f"{book}.dev.capacity_cr", f"{book.upper()} capacity (smaller of half-metric and 20%-cap AUM), Rs crore", DEV, "json", "portfolios_*", "metrics.json", (f"{book}.capacity", "capacity_aum_cr")),
            (f"{book}.dev.break_even_cost_multiple", f"{book.upper()} break-even cost multiple", DEV, "json", "portfolios_*", "metrics.json", (f"{book}.break_even_cost_multiple",)),
            (f"{book}.oos.capacity_cr", f"{book.upper()} capacity, Rs crore", "2024-11-01 -> 2026-10-30", "json", "oos", "metrics.json", (f"{book}.capacity", "capacity_aum_cr"))]
REG += [
    ("combo.lgbm.rank_ic_h1", "LGBM score mean rank IC at h=1 (walk-forward)", DEV, "cell", "combo_*", "combo_decay.csv", ("signal", "LGBM", "1")),
    ("combo.lgbm.rank_ic_h21", "LGBM score mean rank IC at h=21 (walk-forward)", DEV, "cell", "combo_*", "combo_decay.csv", ("signal", "LGBM", "21")),
    ("p0.oos.sharpe_gross", "P0 decile long-short spread, gross Sharpe (holdout)", "2024-11-01 -> 2026-10-30", "json", "oos", "metrics.json", ("p0.sharpe_gross",)),
    ("p0.dev.sharpe_gross", "P0 decile long-short spread, gross Sharpe (weekly, equal weight)", DEV, "json", "portfolios_*", "metrics.json", ("p0.sharpe_gross",)),
    ("data.min_universe", "Smallest monthly universe (names)", "2013-2024", "json", "data_qa", "gate_report.json", ("universe_names_per_month", "min")),
    ("data.months_below_750", "Months with fewer than 750 universe names", "2013-2024", "json", "data_qa", "gate_report.json", ("universe_names_per_month", "months_below_750")),
    ("p1.dev.dsr", "P1 deflated Sharpe, walk-forward (N_all trials)", DEV, "json", "portfolios_*", "metrics.json", ("p1.dev.dsr_n_all",)),
    ("honesty.n_all", "Logged trials (N_all)", DEV, "json", "portfolios_*", "honesty_p1.json", ("n_all",)),
    ("honesty.n_eff", "Effective independent trials (N_eff, rho>0.7)", DEV, "json", "portfolios_*", "honesty_p1.json", ("n_eff",)),
    ("p1.oos.ir_net.ci95_lo", "P1 OOS net IR, bootstrap 95% CI low", "2024-11-01 -> 2026-10-30", "json", "oos", "honesty_p1.json", ("bootstrap_ir_annual", "ci_lo")),
    ("p1.oos.ir_net.ci95_hi", "P1 OOS net IR, bootstrap 95% CI high", "2024-11-01 -> 2026-10-30", "json", "oos", "honesty_p1.json", ("bootstrap_ir_annual", "ci_hi")),
    ("p2.oos.sharpe_net.ci95_lo", "P2 OOS net Sharpe, bootstrap 95% CI low", "2024-11-01 -> 2026-10-30", "json", "oos", "honesty_p2.json", ("bootstrap_sharpe_annual", "ci_lo")),
    ("p2.oos.sharpe_net.ci95_hi", "P2 OOS net Sharpe, bootstrap 95% CI high", "2024-11-01 -> 2026-10-30", "json", "oos", "honesty_p2.json", ("bootstrap_sharpe_annual", "ci_hi")),
    ("oos.score.mean_rank_ic_h5", "Frozen score, OOS mean rank IC (h=5)", "2024-11-01 -> 2026-10-30", "json", "oos", "metrics.json", ("score.oos.mean_rank_ic_h5",)),
    ("oos.score.t_nw_h5", "Frozen score, OOS Newey-West t (h=5)", "2024-11-01 -> 2026-10-30", "json", "oos", "metrics.json", ("score.oos.t_nw_h5",)),
]
IDS = {r[0] for r in REG}


def resolve(row, runs: Path):
    _id, _desc, _win, kind, dpat, fname, path = row
    d = (Path(runs) / dpat) if "*" not in dpat else _latest(runs, dpat)
    if d is None or not Path(d).exists():
        return NOT_RUN, None, None
    p = Path(d) / fname
    v = _costs(p, path[0], path[1]) if kind == "costs" else _sens(p, *path) if kind == "sens" else _cell(p, (path[0], path[1]), col=path[2]) if kind == "cell" else _dig(_json(p), path)
    if path and path[-1] == "capacity_aum_cr" and v is not None:  # capacity is undefined when the book loses money net at Rs 1 crore
        bk, tg = _id.split(".")[:2]
        m = _dig(_json(p), (f"{bk}.{tg}.{'ir' if bk == 'p1' else 'sharpe'}_net",))
        v = "none (net metric <= 0 at Rs 1 crore)" if m is not None and m <= 0 else v
    sha = (_json(p) or {}).get("git_sha") if kind not in ("costs", "sens", "cell") else (_json(p.with_name("metrics.json")) or {}).get("git_sha")
    return (NOT_RUN if v is None else v), (str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p)), sha


def fmt(v) -> str:
    if v == NOT_RUN:
        return v
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, int):
        return f"{v}"
    if isinstance(v, float):
        return f"{v:.3f}"
    return str(v)


def collect(runs: Path = ROOT / "runs") -> list[dict]:
    out = []
    for r in REG:
        v, src, sha = resolve(r, runs)
        out.append({"id": r[0], "desc": r[1], "window": r[2], "value": v, "text": fmt(v), "sha": sha or "-",
                    "source": f"{src}#{'.'.join(r[6])}" if src else "-"})
    return out


def _tex(s: str) -> str:
    return s.replace("\\", r"\textbackslash{}").replace("_", r"\_").replace("%", r"\%").replace("&", r"\&").replace("->", "to")


def write_all(runs: Path = ROOT / "runs", results: Path = ROOT / "RESULTS.md", tex: Path = ROOT / "report" / "numbers.tex") -> dict:
    rows = collect(runs)
    sha = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip() or "unknown"
    lock = _json(ROOT / "oos.lock") or {}
    L = ["# RESULTS ledger", "", "Generated by `qr ledger` from files under `runs/` (git-ignored; rebuild with the README commands). "
         "Every value traces to the file named in its Source column, produced at the git SHA in the last column (the SHA each run recorded about itself); \"not run\" means the file or key does not exist. "
         f"Generated at git `{sha}`; `prereg-v1` commit `{str(lock.get('prereg_commit'))[:10]}`; OOS lock state `{lock.get('state', 'unknown')}`, "
         f"opened_at `{lock.get('opened_at')}`.", "",
         "| ID | Description | Window | Value | Source | Git SHA |", "| --- | --- | --- | --- | --- | --- |"]
    L += [f"| `{r['id']}` | {r['desc']} | {r['window']} | {r['text']} | `{r['source']}` | `{r['sha']}` |" for r in rows]
    Path(results).write_text("\n".join(L) + "\n")
    T = ["% generated by `qr ledger`; do not edit",
         r"\newcommand{\R}[1]{\ifcsname res@#1\endcsname\csname res@#1\endcsname\else\PackageError{numbers}{Undefined result id #1}{Add it to qr.report.ledger.REG.}\fi}"]
    T += [r"\expandafter\def\csname res@%s\endcsname{%s}" % (r["id"], _tex(r["text"])) for r in rows]
    _readme(rows, Path(results).parent / "README.md")
    _bullets(rows, Path(results).parent / "docs" / "RESUME_BULLETS.md")
    _costs_table(Path(tex).parent / "costs_table.tex")
    Path(tex).parent.mkdir(parents=True, exist_ok=True)
    Path(tex).write_text("\n".join(T) + "\n")
    return {"n_rows": len(rows), "n_not_run": sum(r["text"] == NOT_RUN for r in rows)}


HEADLINE = ["oos.score.mean_rank_ic_h5", "oos.score.t_nw_h5", "p1.oos.ir_net", "p1.oos.ir_net.ci95_lo", "p1.oos.ir_net.ci95_hi", "p1.oos.ir_gross", "p2.oos.sharpe_net", "p1.dev.ir_net", "p1.dev.ir_gross",
            "p1.oos.turnover_oneway_pa", "p1.oos.cost_drag_bp", "p1.dev.dsr", "honesty.n_all", "honesty.n_eff", "p1.dev.capacity_cr"]


def _readme(rows: list[dict], path: Path) -> None:
    """Fill the block between the RESULTS markers with headline rows (values copied from the ledger rows)."""
    if not path.exists():
        return
    t = path.read_text()
    a, b = "<!-- RESULTS:BEGIN -->", "<!-- RESULTS:END -->"
    if a not in t or b not in t:
        return
    by = {r["id"]: r for r in rows}
    blk = ["| ID | Quantity | Window | Value |", "| --- | --- | --- | --- |"] + [f"| `{i}` | {by[i]['desc']} | {by[i]['window']} | {by[i]['text']} |" for i in HEADLINE]
    path.write_text(t[: t.index(a) + len(a)] + "\n" + "\n".join(blk) + "\n" + t[t.index(b):])


BULLETS = [
    "Built a survivorship-bias-free NSE daily equity panel from raw exchange archives: {data.n_sessions} sessions and {data.n_sids} securities, including {data.n_delisted_in_univ} later-delisted names that were in the liquid universe, 2012-2026. It merges two exchange file formats, links securities through ISIN and symbol changes, infers split and bonus adjustments from exchange price ratios checked against F&O lot sizes, and builds a point-in-time liquidity universe, and a truncation-based test checks it for look-ahead.",
    "Tested 8 point-in-time cross-sectional signals with Newey-West inference. The strongest sector-, beta- and size-neutral signal by Newey-West t, {sig.best_neu.name}, reached a mean rank IC of {sig.best_neu.rank_ic_h5} (t = {sig.best_neu.t_nw_h5}, 5-day horizon, 2013-2024). {sig.n_pass_holm_t3} of 16 tests cleared a t >= 3 hurdle after Holm correction.",
    "Compared equal-weight z-score, ridge and LightGBM combiners under purged, embargoed walk-forward CV (8 folds). {combo.headline} achieved a rank IC of {combo.headline.rank_ic}, against {combo.ew.rank_ic} for equal weight (paired IC-difference t = {combo.diff_vs_ew.t_nw}).",
    "Modelled Indian execution costs: time-varying STT including the 2026 futures hike, exchange fees, stamp duty, GST, Abdi-Ranaldo spreads and square-root impact. A long-only top-decile book against the Nifty 500 index earned a walk-forward net IR of {p1.dev.ir_net} (gross {p1.dev.ir_gross}), at {p1.dev.turnover_oneway_pa}x one-way turnover a year; capacity: {p1.dev.capacity_cr}.",
    "Enforced research hygiene with a pre-registered protocol, a lock-file-guarded 24-month holdout read once, and {honesty.n_all} logged trials (N_eff = {honesty.n_eff}). Holdout results: long-only net IR {p1.oos.ir_net} (95% CI {p1.oos.ir_net.ci95_lo}, {p1.oos.ir_net.ci95_hi}). F&O long-short net Sharpe {p2.oos.sharpe_net}. Deflated Sharpe {p1.dev.dsr} (development window).",
]
NULL5 = "Holdout net IR was {p1.oos.ir_net} (95% CI {p1.oos.ir_net.ci95_lo}, {p1.oos.ir_net.ci95_hi}). A gross edge of {p1.oos.ir_gross} did not survive {p1.oos.cost_drag_bp} bp a year of costs, {p1.oos.stt_share_pct}% of them STT. Deflated Sharpe {p1.dev.dsr}."


def _fill(t: str, by: dict) -> tuple[str, bool]:
    import re
    miss = False

    def f(m):
        nonlocal miss
        v = by[m.group(1)]["text"]
        miss |= v == NOT_RUN
        return f"[{m.group(1)}]" if v == NOT_RUN else v
    return re.sub(r"\{([^}]+)\}", f, t), miss


def _bullets(rows: list[dict], path: Path) -> None:
    """PRD s13 bullets filled ONLY from ledger values. A bullet with any missing number keeps bracketed ledger-ID placeholders."""
    by = {r["id"]: r for r in rows}
    L = ["# Resume bullets (generated by `qr ledger`)", "", "Values are copied from RESULTS.md. `[id]` = no ledger value yet: do not use that bullet until it is filled. "
         "Lead with OOS numbers; label development numbers walk-forward. Avoid the word \"alpha\" if the OOS CI includes 0 or the DSR is below 0.95; use the null variant.", ""]
    for i, b in enumerate(BULLETS, 1):
        t, miss = _fill(b, by)
        L.append(f"{i}. {t}" + ("  <!-- INCOMPLETE -->" if miss else ""))
    t, miss = _fill(NULL5, by)
    L += ["", f"**Null-result variant of bullet 5.** {t}" + ("  <!-- INCOMPLETE -->" if miss else "")]
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text("\n".join(L) + "\n")


def _costs_table(path: Path) -> None:
    """Cost-assumption table rendered from config/costs.yaml (inputs, not results, but still never hand-typed)."""
    import yaml
    cfg = yaml.safe_load((ROOT / "config" / "costs.yaml").read_text())
    seg = {"eq_delivery": "Delivery", "stk_future": "Stock futures"}
    L = [r"\begin{tabular}{llllr}\toprule", r"Component & Segment & Side & From & Rate (bp) \\ \midrule"]
    for r in cfg["rows"]:
        L.append(f"{_tex(r['component'])} & {seg[r['segment']]} & {r['side']} & {r['valid_from']} & {r['rate'] * 1e4:.3f} \\\\")
    L += [r"\midrule", f"GST on brokerage + exchange + SEBI & & & & {cfg['gst_rate'] * 100:.0f}\\% \\\\",
          f"DP charge per scrip per sell day & Delivery & sell & & Rs {cfg['dp_charge_inr']:.2f} \\\\", r"\bottomrule\end{tabular}"]
    Path(path).write_text("% generated by `qr ledger` from config/costs.yaml\n" + "\n".join(L) + "\n")
