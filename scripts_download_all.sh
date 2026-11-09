#!/usr/bin/env bash
# Resumable full download: recent years first (PRD fallback: sample may start 2016), then 2012-2015.
set -u
cd "$(dirname "$0")"
.venv/bin/qr ingest --start 2016-01-01 --end 2026-10-30 && \
.venv/bin/qr ingest --start 2012-01-02 --end 2015-12-31
