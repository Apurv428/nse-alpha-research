# PROGRESS

_Read this first in a new session. Update at the end of every working session._

## Status (2026-11-09, ~20:40 UTC)
- **Phase:** Day 1 code complete; Day 1 GATE NOT MET yet (data still downloading; corporate-action export missing).
- **Spec:** `docs/PRD.md`. Rules: `CLAUDE.md`. Decisions: `docs/DECISIONS.md` (D-001..D-012).
- **Environment:** cloud workspace, Linux, uv + Python 3.11.18 (`.venv`, `uv.lock`). User machine: Windows x64, local shell
  unavailable (VM won't start). Sync = copy files + `git bundle` into `D:\QR\nse-alpha-research*` (Makefile is protected on the user's drive; it is in the bundle).
- **Data:** `data/` is git-ignored and lives only in this cloud session. Rebuild: `qr ingest` -> `qr bronze` -> `qr panel` -> `qr qa`.

## Download (managed background job, resumable)
- Script `scripts_download_all.sh` (2016-2026 first, then 2012-2015). Run it via a background task with timeout 7200000 and
  RELAUNCH when it exits (it skips everything already in `data/raw/_manifest.jsonl`). ~15.6k requests total, ~0.9 req/s => ~4.7 h.
- Static reference files (sector lists, EQUITY_L, fo_mktlots) already fetched into `data/raw/static/`.

## Done
- Setup (repo, env, CLAUDE.md, PROGRESS.md, DECISIONS.md).
- Guards: `guard/oos_lock.py` (lock SEALED, `oos.lock` committed), `guard/trial_ledger.py` (+ `tests/test_oos_lock.py`).
- Ingest: downloader, 4 bronze parsers (CM legacy/UDiFF, F&O legacy/UDiFF, MTO, index), corporate-action parser (+tests).
- Silver: security master + links, split/bonus/dividend-adjusted total returns, jump audit, PIT universe, fut_cont, bench (approx TRI), sectors, QA gate report.
- 33 tests pass; `tests/test_parsers_overlap.py::test_legacy_udiff_agree_on_overlap` fails until the 2024 overlap files are downloaded (by design: it fails rather than skips).

## Next
1. Wait for download; relaunch the job if it stops. When complete: `qr bronze all && qr panel && qr qa`, read `runs/data_qa/gate_report.json`.
2. USER ACTION needed: drop the yearly corporate-action CSV exports into `data/raw/corpactions/` (via `D:\QR\manual\corpactions\`).
   Without them the "20 actions |r| < 20%" gate cannot pass; splits/bonuses become nulled-return jump flags.
3. Day 1 gate -> commit -> Day 2: write PREREG.md, commit, tag `prereg-v1` BEFORE any IC, then run signals.
- While waiting: Day 2-4 modules are being written and unit-tested on synthetic data only (NO real-data IC/backtest has been run).

## Open issues
- Manual exports still needed from the user: corporate actions (yearly CSV), optional Nifty 500 TRI and RBI T-bill.
- Universe may have < 750 liquid names in early years (Rs 1 crore median-value floor): will be reported, not hidden.

## Numbers produced so far
None (no real-data results computed yet).
