# Commit SHA map (history rewrite of 2026-11-10)

Before the first push, author and committer were set to the owner's GitHub identity and tool trailers were removed from commit
messages (`git filter-branch`, D-035). File trees and commit dates are unchanged, but every SHA changed. Files written before the
rewrite (oos.lock `prereg_commit` and `opened_commit`, `git_sha` in trials/trials.jsonl and runs/*/metrics.json) name the OLD SHAs;
resolve them with this table. Commit dates show that PREREG.md (tag prereg-v1) precedes every result.

| # | Old SHA | New SHA | Commit date and subject |
| --- | --- | --- | --- |
| 1 | `db5e0af07c8a28154f735df55dc06f1566de7c14` | `ea279be5faf279e8f513988800703289da102d7d` | 2026-11-09T20:03:01+00:00 Set up repo skeleton, pinned env, CLAUDE.md, PROGRESS.md, DECISIONS.md |
| 2 | `7738ca408c059b9de86d399aa6c81bf57fdb9fcb` | `b0ea5b9ce83ec22d0ec40ab10fa3215a475aaa63` | 2026-11-09T20:29:37+00:00 Add OOS lock, trial ledger, downloader and bronze parsers |
| 3 | `ec7ba7d70d4a6348394f8a6f84dc4a5005d29961` | `7d2e70ff3350b1c9b6b5a9e87f64738de8f9a868` | 2026-11-09T20:35:58+00:00 Add silver layer: security master, adjusted returns, PIT universe, futures, bench, sectors, QA |
| 4 | `66316876f65e3bac5bea0c0072e8113a67ac0177` | `1cd70795fde9d991b292c355697b45bd1c5b4d2f` | 2026-11-09T20:36:37+00:00 Update PROGRESS and DECISIONS (D-010..D-015) |
| 5 | `0db002527a21339f5c3fe3e6f5fcca2410f549f0` | `11db4250f55f0b1bf4e65c33b5607412729a2b26` | 2026-11-09T20:45:08+00:00 Add signals, gold build, evaluation, statistics, lint test and synthetic end-to-end tests |
| 6 | `8937daae5ff658f81d67f8e050202972de50203a` | `470f3e5b11c6c6c20ce17d47115de3bfda3699c0` | 2026-11-09T20:50:52+00:00 Add walk-forward combiners, cost schedule and cost model, spread/impact inputs |
| 7 | `b2de0ee49ede0dfc959abd5b3e6f9e537375355e` | `2d25c54dd8292aff97e19eb9d12ed196afd847cf` | 2026-11-09T20:53:37+00:00 Add P1/P2 construction, backtest engine, metrics and capacity with synthetic tests |
| 8 | `12c2998ebc9b870828e3b41ff57ebdbbb0bafc2a` | `bae1585e15e72a151190a837758d460b8ea382a0` | 2026-11-09T20:56:07+00:00 Add deflated Sharpe/bootstrap honesty step, fit/backtest CLI, decisions D-021/D-022, progress update |
| 9 | `5fa0385ce340d5561d32d1bcb9c4a937abbed2b1` | `12c576b7bd254f596060e6c6ff433ab9aa4ddc4e` | 2026-11-09T20:56:28+00:00 Pre-register research design (PREREG.md) before any real-data IC |
| 10 | `96f773e42fb609bbded60d2e60d7d8992b8d5e0b` | `eee3972d08faaef2b9ba3d18baf729611b92cf4b` | 2026-11-09T20:56:28+00:00 Record prereg commit in oos.lock |
| 11 | `b69bc0b3f5bd334e97448cdff87fbcd5a167b323` | `eab7f01590161221d41e5d0294587613335451f0` | 2026-11-09T20:59:09+00:00 Add model freeze, qr oos (one-time read with preconditions), OOS rehearsal and refusal-path tests |
| 12 | `27ad5eec92c3457680b7e11623c8ef3c658f273c` | `1f956ed178200b8d5f5c11109e7994e542d448a0` | 2026-11-09T21:01:08+00:00 Add qr ledger (RESULTS.md, numbers.tex) with per-row source and git SHA, hygiene tests |
| 13 | `6e8e10ced15de9648e076c502f3a6011593ea0ab` | `75f0749abe41781287205888a67407c343cb35b8` | 2026-11-09T21:04:58+00:00 Add report skeleton, figures, README, CI, resume-bullet generator |
| 14 | `5c50dcbacb3f97b3354d84bbf96c42b489cbe4e6` | `93e31d80f13478def532b7828d2df493857398ab` | 2026-11-09T21:38:29+00:00 Fix QA label counts and fut_cont join found by a real-data dry run of the data layer |
| 15 | `97e46567601f439d46d50774c5ad03ccea4fc925` | `58590444004e7617d2eddba7854548291f59b1d9` | 2026-11-09T22:31:17+00:00 Progress: download stopped at its time limit (2022-03), resumable |
| 16 | `ed79f3d9e904623ee482563bb4e18c649a9befe1` | `a310f08051bd448ffb83e11525d4105a2d18d1d5` | 2026-11-10T07:26:32+00:00 Infer splits/bonuses by ratio snapping with F&O lot evidence; keep genuine F&O moves; parser fixes from real files |
| 17 | `67e725126879d1f78285092ee625504151301f95` | `21d320d81c6bf6d8f7b908e9c8c21e3466f8ba23` | 2026-11-10T07:26:54+00:00 Match P1 benchmark basis to stock-return basis (price index without dividend data) |
| 18 | `3dd402ee21215dd7b7929b1a29e44d36cef8bf7f` | `6d5da7be1d334118104c32448f3a8a7b66fd4b94` | 2026-11-10T07:27:32+00:00 Downloader: two requests in flight under the same 1 request/s start limiter |
| 19 | `15c31ed1e8f6df78a0d22c87d7f914a685b4c95c` | `c3b4f373930875ca61084906f2a057c403a7e6d5` | 2026-11-10T07:33:07+00:00 Disclose accidental development-window look (D-028), add its 33 trials to the ledger; selection raises on NaN folds; real-data PIT truncation test |
| 20 | `e57213b1f3f326447547a504a6655d1f5785d641` | `774254f85f0ff4499417b1de31c7a959b98abace` | 2026-11-10T07:33:34+00:00 Report/README text for inferred corporate actions, price-index benchmark and the disclosed incident |
| 21 | `799b91a1049948d2005a743919bc9d0c9935220f` | `2b9130389f72de4986e73a9eb20a93415707ca24` | 2026-11-10T07:33:43+00:00 Report data section: inferred corporate actions |
| 22 | `8868f09e6c439e3327b24282b045c6d005954fc4` | `e4f8aca8dae2b868678f30194339ead7c32ec8d9` | 2026-11-10T07:35:09+00:00 Dev pipeline runner with tripwire stops; figures match eval outputs; progress |
| 23 | `f727fa20954490e7eba6b88f2f860b7054cc4441` | `d1fc82ee9a84f60dc6ccd9e028308c1e02960129` | 2026-11-10T07:35:38+00:00 Generate cost table for the report from costs.yaml |
| 24 | `6ca0ae0deb815cd9f03ea516d1cbab4937077c3a` | `1ac03a113e1abe2095452f24d262fbd54b8f7c29` | 2026-11-10T07:38:07+00:00 Index parser: accept month-first dates only when they match the file date |
| 25 | `457b931a9a0937faff5f0d050568ec3838b4ee78` | `5df84ebbe6df5adc19dddbb86a7659f1c754f347` | 2026-11-10T10:22:39+00:00 Parse 2012-15 file quirks, fit full-sample silver build in memory, record QA gate results |
| 26 | `df0653bf6568a3a17b350432468e337436c6e000` | `10d72df7a953029058928b02be2b70b81f8e2d09` | 2026-11-10T10:33:46+00:00 Bound gold-build memory and run the real-data PIT test in subprocesses |
| 27 | `9ca28871ad5baf89b78f15b10957e58c4bc7fc2e` | `6d852532bb1a8436082ff448b36761f3082aa4ac` | 2026-11-10T10:54:56+00:00 Pass the real-data PIT test; hold non-PIT sector labels fixed in it and report their cutoff sensitivity |
| 28 | `b7ca76577a38f51c6967acb8d5138768cc592fbc` | `0b87b98badb4f8f36c979d2019915d972a03a3b3` | 2026-11-10T11:06:49+00:00 Rebalance the books weekly as pre-registered (daily-rebalance bug), correct the frozen benchmark label |
| 29 | `90ac5e5eceb682b77d10b59b4279412a7ccc0e09` | `b6da3d5232766cc94422d18ab3e1167d08360547` | 2026-11-10T11:09:32+00:00 Development run complete: corrected weekly backtest, superseded buggy portfolio trials, re-frozen model, rehearsal |
| 30 | `796c38a33ed1c2179ef791d5a5e3d60e514f45c3` | `f576e51db41cf5a6b3ad1dfec6ee142c2d90576b` | 2026-11-10T13:37:32+00:00 Record user go-ahead for the single OOS read |
| 31 | `5a31d3c3f1aceab2a4ce8b70c16829949cd19267` | `0b4e0c99aafce9b0b5fa69f1bad32182666f6cb8` | 2026-11-10T13:38:46+00:00 Open OOS lock (state: opened) |
| 32 | `a4e6d30d0b6e05055033e4397fffc93b05b12585` | `ad0e36b1954b5ca934b11e5d8d1b882a05fe2eb9` | 2026-11-10T13:41:16+00:00 Mark OOS read (state: read) |
| 33 | `10813f889eac040449e6d7c1b3b0eef7acb9fbb2` | `95f13ba6c6ee93e1153847ac9bdb9a781e158bea` | 2026-11-10T13:42:43+00:00 Add OOS ledger rows, capacity rule for losing books, and report figures |
