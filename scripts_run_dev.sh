#!/usr/bin/env bash
# Development pipeline, each step ONCE (re-running eval/fit/backtest inflates N_all). Stops at the first failure or tripwire.
# Usage: ./scripts_run_dev.sh data     -> bronze, silver, QA gate (no return statistics)
#        ./scripts_run_dev.sh research -> signals, eval, fit, backtest, freeze, rehearse
set -euo pipefail
cd "$(dirname "$0")"
QR=.venv/bin/qr
log() { echo "[$(date -u +%H:%M:%S)] $*"; }
case "${1:-}" in
  data)
    log bronze;  $QR bronze all
    log panel;   $QR panel
    log qa;      $QR qa ;;
  research)
    log signals;  $QR signals
    log eval;     $QR eval | tee runs/_eval_stdout.txt
    if grep -q '"sig.tripwire_hit": true' runs/_eval_stdout.txt; then log "TRIPWIRE: mean rank IC > 0.08. STOP, audit for leakage."; exit 3; fi
    log fit;      $QR fit
    log backtest; $QR backtest 2> runs/_backtest_stderr.txt | tee runs/_backtest_stdout.txt
    if grep -q TRIPWIRE runs/_backtest_stderr.txt; then log "TRIPWIRE: P1 net IR > 2. STOP, audit for leakage."; exit 3; fi
    log freeze;   $QR freeze
    log rehearse; $QR rehearse > runs/_rehearse_stdout.txt
    log done ;;
  *) echo "usage: $0 data|research"; exit 1 ;;
esac
