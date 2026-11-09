import datetime as dt

import numpy as np
import polars as pl

from qr.guard import trial_ledger as L
from qr.stats.honesty import honesty


def weekly(seed, mu=0.0, n=300):
    rng = np.random.default_rng(seed)
    d0 = dt.date(2017, 1, 6)
    return pl.DataFrame({"date": [d0 + dt.timedelta(weeks=i) for i in range(n)], "ret": rng.normal(mu, 0.01, n)})


def test_dsr_uses_true_trial_count_and_penalises_more_trials(tmp_path):
    led, runs = tmp_path / "t.jsonl", tmp_path / "runs"
    for k in range(5):
        L.log_trial("signal", {"k": k}, ("2017-01-06", "2022-10-28"), "W", weekly(k), ledger=led, runs=runs)
    best = weekly(99, mu=0.002)
    L.log_trial("portfolio", {"k": "best"}, ("2017-01-06", "2022-10-28"), "W", best, ledger=led, runs=runs)
    h6 = honesty(best, led, B_=500)
    for k in range(5, 40):
        L.log_trial("signal", {"k": k}, ("2017-01-06", "2022-10-28"), "W", weekly(k), ledger=led, runs=runs)
    h41 = honesty(best, led, B_=500)
    assert h6["n_all"] == 6 and h41["n_all"] == 41
    assert h41["dsr_n_all"]["dsr"] < h6["dsr_n_all"]["dsr"]            # more trials -> a harsher deflation
    assert 0 < h41["psr0"] <= 1 and h41["n_eff"] <= h41["n_all"]
    ci = h41["bootstrap_sharpe_annual"]
    assert ci["ci_lo"] < ci["point"] < ci["ci_hi"]
