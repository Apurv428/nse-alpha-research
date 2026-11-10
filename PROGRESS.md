# PROGRESS

_Read this first in a new session. Update at the end of every working session._

## Status (2026-11-10 13:10 IST)
- **Goal (user):** finish the whole project today. User decisions 12:40 IST: download now (D-024), no corporate-action export (D-023).
- **Download:** running (2 requests in flight, starts >= 1 s apart, D-027); full 2012-2026 sample expected ~15:20 IST. Job limit is 2 h: relaunch
  `./scripts_download_all.sh` if it stops (resumable).
- **Then:** `./scripts_run_dev.sh data` -> read runs/data_qa/gate_report.json -> `QR_RUN_REALDATA=1 uv run pytest tests/test_pit_truncation.py`
  -> `./scripts_run_dev.sh research` (ONCE) -> show the user the frozen model/config -> on explicit go-ahead: tag `oos-candidate`, `qr oos --confirm`
  -> `qr ledger`, `qr figures`, write results/interpretation, `make report`, check numbers trace, sync, ask before any GitHub push.
- **Incident D-028:** an accidental look at partial development results (shuffle no-op); 33 trials added to the ledger; disclosed in the report.
- **Spec:** `docs/PRD.md`. Rules: `CLAUDE.md`. Decisions: `docs/DECISIONS.md` (D-001..D-028).

## Real-data dry run (2026-11-10, partial download 2016-01 .. 2019-06, scratch dir, deleted afterwards)
- bronze -> silver -> qa -> gold -> cost inputs -> backtest panel all run on real files. NO IC, backtest or performance number was computed.
- Bugs found and fixed: (1) QA/silver label counts were paired with the wrong labels (two `value_counts()` calls, unstable order);
  (2) `build_panel` assumed a `sess` column in `silver.fut_cont` (real table is keyed by trade_date). Tests updated to the real schema.
- Observed: ~1,670 unexplained >25% jumps in 3.5 partial years (no corporate-action file yet; the rest were partial-download gap artifacts);
  Unclassified sector share 34-47% of the universe in 2017-2019 (2026 snapshot; PRD limitation, report it); F&O names in universe ~174 (2017).

## Next
1. Wait for download; relaunch the job if it stops. When complete: `qr bronze all && qr panel && qr qa`, read `runs/data_qa/gate_report.json`.
2. USER ACTION needed: drop the yearly corporate-action CSV exports into `data/raw/corpactions/` (via `D:\QR\manual\corpactions\`).
   Without them the "20 actions |r| < 20%" gate cannot pass; splits/bonuses become nulled-return jump flags.
3. Day 1 gate -> commit -> Day 2: PREREG.md BEFORE any real IC (then `set_prereg_commit`); `qr signals && qr eval` ONCE; `qr fit`; `qr backtest`; then `qr oos` (to write) and STOP for user go-ahead.
   (old line: write PREREG.md, commit, tag `prereg-v1` BEFORE any IC, then run signals.
- While waiting: Day 2-4 modules are being written and unit-tested on synthetic data only (NO real-data IC/backtest has been run).

## Open issues
- Manual exports still needed from the user: corporate actions (yearly CSV), optional Nifty 500 TRI and RBI T-bill.
- Universe may have < 750 liquid names in early years (Rs 1 crore median-value floor): will be reported, not hidden.

## Numbers produced so far
None (no real-data results computed yet).
