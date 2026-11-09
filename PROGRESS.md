# PROGRESS

_Read this first in a new session. Update at the end of every working session._

## Status
- **Phase:** Setup complete and verified (4/4 smoke tests pass). Day 1 plan awaiting user review. No data code written.
- **Spec:** `docs/PRD.md` (copy of the user's PRD, sha256 9ba8d60f…ab6). Rules: `CLAUDE.md`. Decisions: `docs/DECISIONS.md`.
- **Environment:** cloud workspace, Linux, uv + Python 3.11. User machine: Windows x64, local shell unavailable
  (VM won't start), so files are synced to `D:\QR\nse-alpha-research\` via file copy + git bundle.

## Done
- Env: Python 3.11.18, uv 0.11.32, polars 2.1.0, duckdb 2.0.0, statsmodels 0.15.0, scipy 1.17.1, scikit-learn 1.9.1, lightgbm 4.7.0, mlflow 3.18.0 (pinned in uv.lock). LaTeX (latexmk/pdflatex) present in the cloud workspace.
- Probed NSE archive host once (HEAD, honest UA): HTTP 200.
- Repo initialised (`main`), skeleton from PRD section 2, `pyproject.toml`, `.gitignore`, `Makefile`, `qr` CLI stub, env smoke test.

## Next
- User approves Day 1 plan, then: seal `oos.lock`, `clip()`, trial-ledger decorator, downloader, parsers, ... (PRD s10 Day 1).

## Open issues
- Data volume: ~11,000 NSE requests at 1 req/s (~3.5 h). Needs a decision on where/how the download runs (see Day 1 plan).
- Manual exports needed from the user (corporate actions per year, sector lists, Nifty 500 TRI, RBI T-bill).

## Numbers produced so far
None.
