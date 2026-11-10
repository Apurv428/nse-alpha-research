# NSE Cross-Sectional Alpha Research

**Question.** Do classic daily price/volume signals predict cross-sectional returns on the NSE after realistic Indian costs, and does the
answer survive an honest, locked holdout?

**Answer.** See the headline table below. It is generated from run files by `qr ledger`; "not run" means that stage has not been executed.
Weak or negative results are reported as plainly as strong ones. Full detail: `report/main.pdf`, audit trail: `RESULTS.md`.

<!-- RESULTS:BEGIN -->
| ID | Quantity | Window | Value |
| --- | --- | --- | --- |
| `p1.oos.ir_net` | P1 net IR vs Nifty 500 (price index) | 2024-11-01 -> 2026-10-30 | not run |
| `p1.oos.ir_net.ci95_lo` | P1 OOS net IR, bootstrap 95% CI low | 2024-11-01 -> 2026-10-30 | not run |
| `p1.oos.ir_net.ci95_hi` | P1 OOS net IR, bootstrap 95% CI high | 2024-11-01 -> 2026-10-30 | not run |
| `p1.oos.ir_gross` | P1 gross IR | 2024-11-01 -> 2026-10-30 | not run |
| `p2.oos.sharpe_net` | P2 net Sharpe on capital | 2024-11-01 -> 2026-10-30 | not run |
| `p1.dev.ir_net` | P1 net IR vs Nifty 500 (price index) | 2017-01-02 -> 2024-10-31 | not run |
| `p1.dev.ir_gross` | P1 gross IR | 2017-01-02 -> 2024-10-31 | not run |
| `p1.dev.dsr` | P1 deflated Sharpe, walk-forward (N_all trials) | 2017-01-02 -> 2024-10-31 | not run |
| `honesty.n_all` | Logged trials (N_all) | 2017-01-02 -> 2024-10-31 | not run |
| `honesty.n_eff` | Effective independent trials (N_eff, rho>0.7) | 2017-01-02 -> 2024-10-31 | not run |
| `p1.dev.capacity_cr` | P1 capacity (smaller of half-metric and 20%-cap AUM), Rs crore | 2017-01-02 -> 2024-10-31 | not run |
<!-- RESULTS:END -->

## What is in here
- A survivorship-free daily NSE panel rebuilt from raw exchange archives (cash, delivery, F&O, index), ISIN-linked, with splits and bonuses inferred from the data (ratio matching confirmed by F&O lot sizes; no dividends) and a point-in-time monthly liquidity universe.
- 8 pre-registered signals, evaluated with rank IC, Newey-West inference and Holm correction; EW / ridge / LightGBM combiners under purged, embargoed walk-forward CV.
- Long-only (P1, vs the Nifty 500 price index: stock returns exclude dividends) and F&O long-short (P2) books, gross and net of a time-varying Indian cost model (STT history incl. the April 2026 futures hike), with turnover and capacity.
- Research hygiene: `PREREG.md` + tag `prereg-v1` before the first IC; `oos.lock` (holdout 2024-11-01 to 2026-10-30, read once); an append-only trial ledger; deflated Sharpe with the true trial count.

## Setup
```bash
uv sync --python 3.11        # pinned in uv.lock
uv run pytest -q             # CI sets QR_ALLOW_NO_DATA=1 so data-dependent tests skip
```

## Rebuild the data and results (data/ and runs/ are not in git)
```bash
uv run qr ingest --start 2012-01-02 --end 2026-10-30   # polite: <=1 request/s, cached, resumable (hours)
# optional manual inputs (not used in the reported run): corporate-action CSV exports -> data/raw/corpactions/
uv run qr bronze all && uv run qr panel && uv run qr qa   # read runs/data_qa/gate_report.json
uv run qr signals && uv run qr eval                        # logs 16 signal trials
uv run qr fit && uv run qr backtest                        # combiners, then P0/P1/P2 on the development window
uv run qr freeze && uv run qr rehearse                     # freeze the headline model; mechanics-only rehearsal (sealed)
# tag the frozen commit `oos-candidate`, then (after explicit sign-off) the one-time read:
uv run qr oos --confirm
uv run qr ledger && uv run qr figures && make report       # RESULTS.md, report/numbers.tex, figures, report/main.pdf
```
The holdout is read once. `qr oos` refuses unless the tree is clean, HEAD is tagged `oos-candidate`, the lock is sealed and the
frozen model hash matches the lock; a second run is refused.

## Limitations (short; full list in the report)
Sector labels are a 2026 snapshot; no shares-outstanding data; corporate-action coverage depends on NSE's export; delisting returns are
unknown (0% / 30% haircut); some historical statutory dates are spot-checked, not independently confirmed; the impact model is a square-root law
not fitted to Indian execution data; the trial count is a lower bound; the researcher knows what happened in 2024-2026 markets.

## Layout
`src/qr/{ingest,panel,signals,eval,stats,models,portfolio,guard,report}`, `config/`, `docs/PRD.md` (spec), `docs/DECISIONS.md`, `PROGRESS.md`, `tests/`, `report/`.
