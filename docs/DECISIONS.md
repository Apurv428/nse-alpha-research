# DECISIONS

Ambiguities in the PRD and environment changes, with the simpler option chosen. Newest last.

## D-001 — Repo name and location (Setup)
PRD layout names the root `nse-alpha/`; the user asked for `nse-alpha-research`. Used the user's name.
The repo is built in the cloud workspace (the user's computer shell was unavailable: its VM would not start).
After each day the working tree is copied to `D:\QR\nse-alpha-research\` and a `git bundle` is written to
`D:\QR\nse-alpha-research.bundle` so the full history can be cloned locally.
*Why simplest:* no way to run git on the user's drive from here; a bundle preserves history exactly.

## D-002 — Python and environment (Setup)
PRD: Python 3.11 + uv, lock file committed. Pinned `requires-python = ">=3.11,<3.12"`; `uv.lock` committed.
The user's own OS is Windows x64 (Python version there is unknown; not probed because the local shell was
unavailable). Anyone on Windows runs `uv sync --python 3.11`; `uv` installs 3.11 itself.

## D-003 — Commit author identity (Setup)
Commits are authored with the user's account email for attribution only. The email is never used in any
HTTP header (see D-004). Before pushing publicly the user may want to switch to a noreply address.

## D-004 — HTTP User-Agent (Setup)
Downloader will send `nse-alpha-research/0.1 (personal research project)`: honest, no personal email (non-negotiable 6).

## D-005 — 404 handling in the downloader (Day 1)
PRD: "3 retries with backoff; a weekday that still returns 404 after retries is a holiday". Retrying a 404 three
times with backoff would waste ~800 requests on holidays. Used: a 404 is re-checked once (2 s later), then recorded as
`missing` in `data/raw/_manifest.jsonl`. 403/429/5xx and network errors use 3 retries with exponential backoff
(honouring Retry-After); persistent 403/429 raises `Blocked` and stops the run (never circumvented).

## D-006 — oos.lock sealed on Day 1, prereg_commit filled on Day 2 (Day 1)
PRD s9 shows `prereg_commit` in the lock at creation, but the prereg commit (Day 2) does not exist yet on Day 1.
The lock is sealed now with `prereg_commit: null`; `oos_lock.set_prereg_commit()` fills it once, while sealed, when
`prereg-v1` is tagged, before any IC is computed.

## D-007 — Trial ledger supersession is an appended event (Day 1)
PRD puts `superseded_by` inside each trial line but also says the ledger is append-only. Supersession is therefore an
appended `{"event":"supersede"}` line; `load_trials()` resolves it. Superseded trials still count toward N_all.

## D-008 — Download order and index start (Day 1)
Probed: legacy F&O ends 2024-07-05 (07-08 is 404); UDiFF F&O exists from at least 2024-01-02; `ind_close_all` exists from
mid-2012 (2012-01-03 is 404). Index files are therefore requested for the whole range. Download order is 2016-2026 first,
then 2012-2015, so the PRD fallback "start in 2016" stays available if the 2012-2015 chunk is late.

## D-009 — Index name changed in 2013 (Day 1)
`ind_close_all` calls the benchmark "S&P CNX 500" in 2013 and "Nifty 500" later; the benchmark builder maps both.

## D-010 — Rights issues left unadjusted (Day 1)
PRD s4 needs the face value at the time of the rights issue (issue price S = FV + premium); the export has no FV and the
EQUITY_L snapshot only has today's. Rights are parsed and counted but NOT price-adjusted (PRD Day 1 cut-list item 2). Any
day with |r| > 25% on a name with an unadjusted event is nulled and logged (`unadjusted_event_nulled`). Counts go to RESULTS.md.

## D-011 — Demerger exclusion is past-only (Day 1)
PRD: exclude a demerged sid 5 sessions either side of the ex-date. The universe is rebuilt monthly on data up to the prior
close, and a future ex-date is not point-in-time information in our data (the export has no announcement date). So the
universe excludes only sids with a demerger ex-date in the last 5 sessions before the as-of date; the ex-date return itself is nulled.

## D-012 — Link rule (a) does not require a corporate-actions file (Day 1)
PRD: link a same-symbol / new-ISIN pair when it follows a split/bonus/demerger within 5 sessions. Implemented as: same symbol,
new ISIN, no overlapping trading and <= 5 sessions between old last trade and new first trade. When a corporate-actions export
is present the reason string also records `+corp_action` if one explains it. Rationale: a CA-gated rule would silently drop
every ISIN-change link if the export is incomplete. A reused symbol after a long gap is correctly NOT linked (tested).

## D-013 — Jump-audit resolution rules (Day 1)
|r| > 25% after adjustment is flagged and resolved as: `halt_gap_kept` (the name did not trade for >= 1 session: a multi-day
move is real), `demerger_nulled`, `unadjusted_event_nulled` (rights etc.), `action_residual_nulled` (an adjusted action still
leaves a big move: wrong ratio), else `unexplained_nulled`. Nulled returns are missing observations, never zeros. The audit
uses only row-t data, so it is point-in-time. Real large moves that are nulled are a limitation (counts reported).

## D-014 — "20 hand-checked actions" (Day 1)
No independent source of 20 verified corporate actions is available offline, and typing them from memory would be
unverifiable. The gate check is therefore: the 20 most liquid split/bonus events in the development window (selected by
code from the export) must have |r| < 20% on the ex-date with a non-null return, plus the two named PRD examples (IRCTC
2021-10-28, INFY 2018-09-04). The list is printed in `runs/data_qa/gate_report.json` for the user to eyeball. This is an
automated spot check, not a manual verification, and is described that way in RESULTS.md.

## D-015 — Series kept in bronze (Day 1)
Bronze keeps only EQ, BE, BZ rows (PRD fixed decision "Price rows kept") and stock futures (FUTSTK / STF). Other series (SME,
gold bonds, G-secs, N-series debt) are dropped at parse time.

## D-016 — "Bit-identical" PIT test needs deterministic numerics (Day 1-2)
Raw signals are bit-identical under truncation with default multithreading. The cross-sectional z and z_neu columns
are not run-to-run bit-identical under multithreading even when the SAME data is rebuilt (Polars group-by and BLAS
reductions differ at ~1e-15/1e-12). The test suite therefore runs single-threaded (`tests/conftest.py`), where the
truncation tests assert exact equality of raw, z and z_neu. `neutralize()` sorts rows by sid so lstsq is reproducible.
Production runs stay multithreaded; their only difference from a single-threaded rebuild is that float noise.

## D-017 — Dimson beta (Day 2)
PRD: "Dimson's sum of the lag-0 and lag-1 betas". Implemented as the sum of two univariate rolling slopes (stock log
return on market log return at lag 0 and lag 1, 252 sessions, >= 150 observations), shrunk 0.6*b + 0.4. A full two-regressor
Dimson regression is not used (simpler; closed-form rolling sums). Missing betas are set to 1.0 (the shrink prior); the
fill rate is reported.

## D-018 — Marginal decay indexing (Day 2)
PRD: "rank IC of z_t against the 1-day return at session t+1+k, k = 0..20". Literally k=0 is the session t+1 return, which is
earned BEFORE the fill at close t+1 (PRD s6 itself says R(h) starts at t+2). Used: the 1-day return of session t+2+k, so k=0
is the first tradable day and equals the h=1 label; half-life is the first k where the IC falls below half the k=0 value.

## D-019 — DSR worked-example check (Day 2)
The paper's own DSR numeric example could not be retrieved offline. Validated instead: (1) PSR against the published
hedge-fund example from Lopez de Prado's Sharpe-ratio presentation (24 monthly returns, SR 0.458, skew -2.448, kurt 10.164
gives PSR(0) 0.913 non-normal and 0.982 normal) to 3 decimals; (2) DSR with one trial equals PSR(0); (3) the expected-max
formula against a Monte Carlo of the maximum of N Sharpe ratios; (4) the DSR of the best of 50 noise strategies < 0.95.
The paper's own DSR example is NOT reproduced; this is stated in the report's limitations.

## D-020 — Truncation test scope (Day 2)
PRD: rebuild silver and gold from raw files truncated at c. The synthetic end-to-end test (tests/test_gold_eval_synthetic.py)
rebuilds universe, gold signals and neutral scores from price rows truncated at c and asserts exact equality for dates <= c.
The full raw -> bronze -> silver truncation on real data is run once the real data exists (tests/test_pit_truncation.py).
