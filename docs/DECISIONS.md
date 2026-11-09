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
