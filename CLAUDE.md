# CLAUDE.md — rules for any session working on this repo

Spec: `docs/PRD.md` (treat as the spec). Where it is ambiguous, choose the simpler option that keeps the
research honest and record the decision in `docs/DECISIONS.md`.
Resume from `PROGRESS.md` alone: read it first, update it at the end of every working session
(done / next / open issues).

## Non-negotiables

1. **Point-in-time only.** No signal, filter, universe or adjustment may use information after its
   timestamp. Every leakage rule gets a test (`tests/test_pit_truncation.py`, `test_cv_purge.py`, ...).
2. **Locked out-of-sample period (2024-11-01 → 2026-10-30), read exactly once**, enforced by `oos.lock`.
   Before running `qr oos --confirm`, STOP and ask the user for explicit go-ahead and show the frozen
   model and portfolio config. Never re-run it after the lock state is `read`. Dev code must load data only
   through `qr` loaders that call `guard.oos_lock.clip()`.
3. **Log every trial** (signal variant, parameter, model, portfolio rule) to `trials/trials.jsonl`
   (append-only, written before results print). The deflated Sharpe uses the true trial count.
4. **Never invent, round up or hand-type results.** Every number in RESULTS.md, README and the report must
   trace to a file under `runs/` written by code. If a number does not exist, write "not run", not an estimate.
5. **Report weak or negative results as plainly as strong ones.** Include a limitations section.
6. **Data access:** polite use of NSE (<=1 request/s, retries with backoff, honest User-Agent with NO
   personal email, on-disk cache, never re-download a cached file). If NSE blocks or changes an endpoint, do
   NOT work around it: switch to the PRD section 3 fallback and record it in `docs/DECISIONS.md`.
   `data/` and `runs/` stay out of git; document how to rebuild them.
7. **Costs:** every portfolio result is reported before AND after the PRD Indian cost model, with turnover
   and capacity.

## Working conventions

- Follow PRD section 10 day by day. At the end of each day: check gate criteria, run tests, commit, update
  PROGRESS.md, give the user a short status (done / numbers produced / anything cut).
- If behind, use the PRD "cut if behind" lists; never cut the lock, the trial ledger or the PIT tests.
- Python 3.11, `uv` (commit `uv.lock`), Polars for transforms. Plain functions, not a framework.
- Commit messages are clear and imperative. Ask the user before creating a GitHub remote or pushing.
- Fixed decisions in PRD section 1 change only before Day 1; a later change is a new trial in the ledger.
