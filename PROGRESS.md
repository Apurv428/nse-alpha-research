# PROGRESS

_Read this first in a new session. Update at the end of every working session._

## Status (2026-11-10 ~16:45 IST)
- **Goal (user):** finish the whole project today. User decisions 12:40 IST: download now (D-024), no corporate-action export (D-023).
- **Data:** full download done (15,628 manifest lines; 282 files of 2012-2015 not served by NSE). Bronze/silver/QA built (D-029, D-030).
- **Real-data PIT test:** PASSED at 3 random cutoffs (runs/pit_realdata.log; sector labels held fixed, D-032).
- **Official dev run:** signals -> eval -> fit -> backtest -> freeze -> rehearse done. No tripwire.
  Backtest bug found and fixed (books rebalanced daily, D-033); backtest re-run, buggy trials superseded (still counted in N_all).
- **NOW WAITING for the user's explicit "go"** to read the locked OOS window once (`qr oos --confirm`). Frozen model: config/frozen/frozen.json
  (LGBM, 8 features, trained 2013-02-01..2024-09-24, best_iteration 78); portfolio config in oos.lock `headline`.
- **After go:** tag `oos-candidate`, `qr oos --confirm` (once) -> `qr ledger`, `qr figures` -> results text in report -> `make report`
  -> check numbers trace -> PROGRESS, commit -> bundle to D:\QR -> ASK before any GitHub remote/push.
- **Spec:** `docs/PRD.md`. Rules: `CLAUDE.md`. Decisions: `docs/DECISIONS.md` (D-001..D-033).

## Development-window numbers (all from runs/, not yet in RESULTS.md; `qr ledger` will copy them with sources)
- eval_20261110T105644, combo_20261110T110053, portfolios_20261110T110704 (weekly, corrected), rehearse output in runs/_rehearse_stdout.txt.

## Open issues
- Universe < 750 names before ~2018 (Rs 1 crore floor binds, D-030); sessions 243/244 in 2014/2019 (election holidays, D-030).
- Sector labels non-PIT (2026 snapshot): cutoff sensitivity in gate_report.json (D-032).
- No dividends: stock returns are price returns, benchmark is the Nifty 500 price index (D-026).
- No RBI T-bill series: constant 6.5% risk-free fallback.
