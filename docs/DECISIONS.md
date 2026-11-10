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

## D-021 STT history verification (2026-11-09/10)
Confirmed from web sources: stock-futures STT 0.0125% from 2023-04-01 (Wikipedia) and 0.02% -> 0.05% effective 2026-04-01
(Business Today). The 2024-10-01 step to 0.02% is consistent with those pages but not independently confirmed from the pages
fetched; delivery 0.1% is confirmed as of 2016, the 2013-06-01 date is not. No reported number depends on pre-2016 rates
(portfolios start 2017-01), so the unconfirmed dates cannot affect results. Brokerage is an assumed institutional-style
3 bp (delivery) / 1 bp (futures), with 0 and 5 bp sensitivities.

## D-022 Portfolio engine simplifications
- Risk-free is the constant 6.5% fallback (no RBI T-bill series supplied); labelled as such in metrics.json.
- One LightGBM configuration (fixed in `combiners.LGBM_PARAMS`), no tuning, so 24 combo trials, not a grid.
- P2 shorts use the cash-market 63-day ADV/sigma/half-spread for the 10% participation cap and impact (futures traded value is
  not carried into silver). Futures roll cost = statutory buy+sell on the short notional plus two half-spreads.
- Short margin (20% of long notional) is held in cash earning rf; P2 capital = long notional + margin.
- A held name with no price carries flat for up to 10 sessions, then is written off at (1 - haircut); base haircut 0%, sensitivity 30%.
- Sensitivity and capacity runs are not logged as trials (same signal, same rule, different cost assumptions); only the base P1 and
  P2 net books are. This is stated in the report.
- Nifty 500 TRI is approximate (price index + dividend yield) unless a manual TRI file is supplied; flagged `tri_is_approx`.

## D-023 Corporate actions without NSE's export: ratio snapping with F&O lot evidence (2026-11-10)
The user chose not to export NSE corporate-action files (one-time manual step) so the project could finish today. Tried first: the
bhavcopy's own PREVCLOSE. Real files show it is NOT split-adjusted (IRCTC 2021-10-28, EICHERMOT 2020-08-24: PREVCLOSE = prior close),
so it cannot supply factors (code kept, off by default). Implemented the PRD s11 fallback instead, with one refinement the real data
forced: the PRD's jump rule assumes +-20% price bands, but F&O stocks have none, and the audit was nulling genuine moves (SBIN +28%
2017-10-25, PNB +46%, YESBANK -56% 2020-03-06, DHFL, JETAIRWAYS). Rule for a non-gap day with |r| > 25% and no export event:
- price ratio within 12% of a common split/bonus/consolidation ratio {1/10, 1/5, 1/4, 1/3, 2/5, 1/2, 3/5, 2/3, 3/4, 2, 5, 10}:
  - non-F&O stock (band <= 20%, so a >25% one-day move cannot be genuine): treat as that action, f = ratio;
  - F&O stock: treat as that action only if the implied lot of the most traded contract alive on both days (value / contracts / close)
    moved by ~1/f (within 10%); else open interest of contracts alive on both days (within 10%). NSE changes the lot of existing contracts
    only for a corporate action, so a genuine crash shows lot ~ unchanged.
- no ratio match: F&O stock -> genuine move, kept (`fno_genuine_kept`), unless OI jumped >= 1.8x with the lot unchanged
  (demerger-like: KPIT 2019-01-24, TATACHEM 2020-03-04) -> nulled; non-F&O stock -> nulled and logged (`unexplained_nulled`).
- never across a market-calendar hole (> 7 calendar days since the previous session).
Validated on 2016-2022 files: PRD known answers IRCTC 2021-10-28 (f = 1/5) and INFY 2018-09-04 (f = 1/2) pass; the 10 most liquid snapped events
(TCS, RELIANCE, M&M 1:1 bonus; HDFCBANK 1:2 split; GAIL 1:3; ITC 1:2; IEX 2:1; EICHERMOT 1:10) match actions the researcher knows of
(checked from memory, not from an exported source). Known weaknesses: dividends are not captured, so stock returns are PRICE returns, and
P1 is therefore compared with the Nifty 500 PRICE index, not the TRI (apples to apples; see D-026); rights issues are captured only when
their ratio is near a common one (e.g. M&MFIN 2020-07-22); demergers in non-F&O names are nulled; an F&O demerger without an OI jump would
be kept as a fake move. All counts are in runs/data_qa/gate_report.json; top-50 snapped events in snapped_top50_for_review.csv.

## D-024 Download outside the PRD's suggested hours (2026-11-10)
The PRD suggests downloading after 19:00 IST or at weekends. On 2026-11-10 the user chose to continue at 12:40 IST to finish the same day.
Unchanged: <= 1 request/s (start to start), honest User-Agent without personal data, cache, retries with backoff, stop on 403/429.

## D-025 Real-data parser quirks (2026-11-10)
- cm legacy 2020-07-13 uses a two-digit year in TIMESTAMP ("13-Jul-20"): parser accepts both formats; the in-file date must still equal the file date.
- Some F&O legacy files write integer columns as decimals ("2630.0000000"): integer columns are cast via Float64.
- Weekend special sessions (Muhurat, budget Saturdays) are never downloaded (weekday requests only). The next session's return then spans
  two sessions; this is correct for returns and is not adjusted.

## D-026 P1 benchmark basis follows the stock-return basis
Without corporate-action exports there are no dividends in stock returns (D-023), so P1 is measured against the Nifty 500 PRICE index
(`n500_close`), not the approximate TRI: comparing a price-return book with a total-return index would understate active return by roughly
the index dividend yield (about 1-1.5% a year). If dividend data is added later, `build_panel` switches to the TRI automatically.
P2's long cash leg also misses its dividends (conservative); the short futures leg is unaffected (dividends are in the futures basis).

## D-027 Two requests in flight, starts still >= 1 s apart (2026-11-10)
Server latency was ~1.9 s per file, so a strictly sequential client ran at ~0.5 request/s. The downloader now keeps up to two requests
in flight while a global lock keeps request STARTS at least 1 s apart, i.e. still <= 1 request/s (test: test_download_limiter_*).
