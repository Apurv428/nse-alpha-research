# Pre-registration v1 (tag `prereg-v1`)

Written 2026-11-10, BEFORE any real-data information coefficient, backtest or model fit was computed. At this point the only
code run on real data is the downloader. Everything below is fixed; a later change gets a new tag (`prereg-v2`, ...) and an
explanation in the report. Spec: `docs/PRD.md`; fixed parameters: `config/research.yaml`, `config/costs.yaml`.

## Windows
- Sample 2012-01-02 -> 2026-10-30. Development 2013-02-01 -> 2024-10-31. Locked OOS 2024-11-01 -> 2026-10-30, read once via `oos.lock`.
- Portfolio development window starts 2017-01-02 (first walk-forward test fold with enough training history).

## Signals, signs, windows (PRD section 5; orientation = higher score, higher expected return, all signs +1)
MOM_12_1 (231 sessions, skip 21, min 200), REV_5 (5, min 4), LOWVOL_63 (63, min 50), IVOL_63 (63, min 50, market model on Nifty 500),
AMIHUD_63 (63, min 50), ABVOL_5_63 (63, min 45), DELIV_ABN (231, min 180), HIGH52 (252, min 200).
Processing: winsorize 1/99, z-score, neutralize (sector dummies, shrunk Dimson beta, size), re-standardize. A negative IC does
NOT flip a sign; a flipped or new variant is a new logged trial.

## Evaluation and hurdles (PRD section 6)
Rank IC at h = 1, 5, 10, 21 on cross-sectional forward returns; Newey-West t (lag per `nw_lag`), ICIR, Holm adjustment across
the 8 signals. A signal "passes" at Holm-adjusted p < 0.05 and t >= 3 at h = 5 on the neutralized score. Tripwire: mean rank IC > 0.08
at h = 5 for any signal, or P1 net IR > 2.0 on the development window => stop and audit for leakage before anything else.

## Models and headline rule (PRD section 7)
Combiners: EW (equal weight of z_neu, missing = 0), ridge (alpha in {0.1, 1, 10, 100, 1000} by inner purged validation), LightGBM
(single fixed configuration in `src/qr/models/combiners.py`, no tuning). Target: Gaussian cross-sectional rank of the 5-day forward
return. Expanding walk-forward, 8 folds, purge 6 + embargo 21 sessions (gap 27), training on every 5th date.
Headline: the better of ridge and LightGBM by mean fold rank IC must beat EW with Newey-West t >= 2 on the daily IC difference at h = 5;
otherwise EW is the headline. No other selection.

## Portfolios and costs (PRD section 8)
P0 paper D10 - D1 (no costs). P1 (headline) long-only, equal weight, enter top 10% / hold to top 20%, weekly, signal at the week's last
close and fill at the next close, 10% of 63-day ADV participation cap, benchmark Nifty 500 TRI (approximate unless a manual file is supplied).
P2 long top quintile in cash / short bottom quintile in near-month stock futures (roll 3 sessions before expiry), F&O universe, capital =
long notional + 20% margin. Costs from `config/costs.yaml` (time-varying STT and the rest), Abdi-Ranaldo half-spread clipped to
[2, 50] bp, square-root impact with Y = 1 (sensitivities 0.5, 2.0), brokerage 3 bp delivery / 1 bp futures (sensitivities 0, 5 bp). Risk-free:
constant 6.5% fallback unless an RBI series is supplied. Capacity grid Rs 1/10/50/100/250/500/1000 crore; break-even cost multiple.
Every result is reported gross and net, with turnover and capacity.

## Honesty
Every signal, combiner fold and base portfolio is logged to `trials/trials.jsonl` before it prints. Deflated Sharpe uses N_all (all logged
trials) and N_eff (clusters at rho > 0.7); bootstrap CIs: stationary block bootstrap, mean block 4 weeks, 10,000 resamples, fixed seed.
The OOS window is read once (`qr oos --confirm`, after explicit user approval of the frozen model and portfolio configuration).
