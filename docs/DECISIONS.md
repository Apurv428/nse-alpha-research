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
