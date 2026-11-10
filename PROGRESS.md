# PROGRESS

_Read this first in a new session. Update at the end of every working session._

## Status (2026-11-10 ~20:00 IST): project complete
- **Data:** full 2012-2026 download (15,628 manifest lines; 282 files of 2012-2015 not served by NSE). QA gates: see D-030.
- **Real-data PIT test:** passed at 3 random cutoffs (D-032).
- **Development run:** eval, fit (LGBM selected by the pre-registered rule), weekly backtest (daily-rebalance bug fixed first, D-033), freeze, rehearse.
- **Holdout:** read ONCE on 2026-11-10 after the user's go-ahead (D-034). `oos.lock` state `read`. Never re-run.
- **Deliverables:** `RESULTS.md` (109 rows, 0 "not run"), `report/main.pdf` (9 pages), `docs/RESUME_BULLETS.md`, README headline block.
- **Git:** history rewritten to `Apurv428 <apurvsonawane28@gmail.com>`, no tool trailers (D-035, map in docs/SHA_MAP.md).
  Remote: https://github.com/Apurv428/nse-alpha-research (main pushed 2026-11-10). Tags prereg-v1 (12c576b) and oos-candidate
  (f576e51) could not be pushed from the cloud workspace; push them from a local clone (`git push origin --tags`).

## Headline (from RESULTS.md, do not retype elsewhere)
Signals survive the holdout (rank IC row `oos.score.mean_rank_ic_h5`); the pre-registered weekly books do not survive Indian costs
(`p1.oos.ir_net`, `p2.oos.sharpe_net`), mostly because of turnover (`p1.oos.turnover_oneway_pa`) and spreads/STT.

## Next (only if continuing)
- A NEW pre-registered study of slower books (monthly rebalance, wider buffer, turnover penalty) needs a NEW holdout; this one is spent.
- Optional: supply dividends / Nifty 500 TRI / RBI T-bill series and rebuild (they change levels, not the conclusion's mechanism).

## Open issues
- Universe < 750 names before ~2018 (Rs 1 crore floor); sessions 243/244 in 2014/2019 (election holidays); sector labels non-PIT.
