# PROGRESS

_Read this first in a new session. Update at the end of every working session._

## Status (2026-11-10)
- **Phase:** Day 1 code complete, Day 1 GATE NOT MET (download ~1.5k of 15.6k manifest lines, at 2017-06; no corporate-action export).
  Day 2-4 code is complete and unit-tested on synthetic data only: signals, eval, stats, CV, combiners, cost model, P1/P2 engine,
  capacity, DSR/bootstrap honesty. CLI: `ingest bronze panel qa signals eval fit backtest`. Also written: `freeze`, `rehearse`, `oos` (refuses unless preconditions hold), `ledger` (RESULTS.md, numbers.tex, README block, docs/RESUME_BULLETS.md), `figures`, LaTeX report skeleton (`report/`, compiles, all results via `\R{id}`), README, CI. All results currently print `not run`.
- **Spec:** `docs/PRD.md`. Rules: `CLAUDE.md`. Decisions: `docs/DECISIONS.md` (D-001..D-022).
- **Environment:** cloud workspace, Linux, `uv run` (Python 3.11, `.venv`, `uv.lock`). User machine: Windows x64, local shell
  unavailable. Sync = copy files + `git bundle` into `D:\QR\nse-alpha-research*` (last sync was after Setup only: refresh needed).
- **Data:** `data/` is git-ignored and lives only in this cloud session. Rebuild: `qr ingest` -> `qr bronze` -> `qr panel` -> `qr qa`.

## Download (managed background job, resumable)
- Script `scripts_download_all.sh` (2016-2026 first, then 2012-2015). Run it via a background task with timeout 7200000 and
  RELAUNCH when it exits (it skips everything already in `data/raw/_manifest.jsonl`). ~15.6k requests total, ~0.9 req/s => ~4.7 h.
- Static reference files (sector lists, EQUITY_L, fo_mktlots) already fetched into `data/raw/static/`.

## Done
- Setup (repo, env, CLAUDE.md, PROGRESS.md, DECISIONS.md).
- Day 2-4 modules (synthetic-tested): signals/gold, eval (IC, decay, deciles), stats (NW, bootstrap, DSR, honesty), models (purged CV, EW/ridge/LGBM), portfolio (costs, impact, construct, backtest, metrics, capacity, run).
- Guards: `guard/oos_lock.py` (lock SEALED, `oos.lock` committed), `guard/trial_ledger.py` (+ `tests/test_oos_lock.py`).
- Ingest: downloader, 4 bronze parsers (CM legacy/UDiFF, F&O legacy/UDiFF, MTO, index), corporate-action parser (+tests).
- Silver: security master + links, split/bonus/dividend-adjusted total returns, jump audit, PIT universe, fut_cont, bench (approx TRI), sectors, QA gate report.
- 117 tests pass; `tests/test_parsers_overlap.py::test_legacy_udiff_agree_on_overlap` fails until the 2024 overlap files are downloaded (by design: it fails rather than skips).

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
