import datetime as dt
import json

import polars as pl
import pytest

from qr.guard import oos_lock as L
from qr.guard import trial_ledger as T


@pytest.fixture
def lock(tmp_path):
    p = tmp_path / "oos.lock"
    L.seal(p)
    return p


def frame():
    d = [dt.date(2024, 10, 30), dt.date(2024, 10, 31), dt.date(2024, 11, 1), dt.date(2026, 10, 30)]
    return pl.DataFrame({"trade_date": d, "label_end_date": [dt.date(2024, 11, 5), dt.date(2024, 10, 31), d[2], d[3]], "x": [1, 2, 3, 4]})


def test_sealed_loader_returns_no_rows_after_dev_end(lock):
    out = L.clip(frame(), path=lock)
    assert out["trade_date"].max() <= dt.date(2024, 10, 31)
    assert out.height == 2
    # lazy frames are clipped too
    assert L.clip(frame().lazy(), path=lock).collect().height == 2


def test_labels_ending_after_dev_end_dropped(lock):
    out = L.clip(frame(), label_end_col="label_end_date", path=lock)
    assert out["x"].to_list() == [2]


def test_missing_lock_refuses(tmp_path):
    with pytest.raises(L.OOSLockError):
        L.clip(frame(), path=tmp_path / "nope.lock")


def test_seal_not_recreatable(lock):
    with pytest.raises(L.OOSLockError):
        L.seal(lock)


def test_open_requires_headline_and_is_once_only(lock):
    with pytest.raises(L.OOSLockError):
        L.mark_opened("abc", lock)  # no headline
    L.set_headline("EW", {"book": "P1"}, lock)
    L.mark_opened("abc123", lock)
    assert L.state(lock) == "opened"
    assert L.clip(frame(), path=lock).height == 4  # open for the one run
    L.mark_read("deadbeef", lock)
    assert L.state(lock) == "read"
    with pytest.raises(L.OOSLockError):  # a second run is refused
        L.assert_can_open(lock)
    with pytest.raises(L.OOSLockError):
        L.mark_opened("abc123", lock)


def test_prereg_commit_set_once(lock):
    L.set_prereg_commit("sha1", lock)
    with pytest.raises(L.OOSLockError):
        L.set_prereg_commit("sha2", lock)


def test_repo_lock_is_sealed_or_read_and_dates_match():
    lk = L.read()
    assert lk["dev_end"] == "2024-10-31" and lk["oos_start"] == "2024-11-01" and lk["oos_end"] == "2026-10-30"


# ---- trial ledger ----
def rets(n=60):
    import numpy as np
    r = np.random.default_rng(1).normal(0.001, 0.02, n)
    return pl.DataFrame({"date": [dt.date(2020, 1, 1) + dt.timedelta(days=7 * i) for i in range(n)], "ret": r})


def test_ledger_is_appended_before_result_returned_and_counts(tmp_path, monkeypatch):
    led = tmp_path / "trials.jsonl"
    seen = {}
    rec1 = T.log_trial("signal", {"sig": "MOM_12_1"}, ("2017-01-02", "2024-10-31"), "W", rets(), ledger=led, runs=tmp_path / "runs")
    rec2 = T.log_trial("combo", {"m": "ridge"}, ("2017-01-02", "2024-10-31"), "W", rets(), ledger=led, runs=tmp_path / "runs")
    assert T.n_all(led) == 2
    lines = led.read_text().splitlines()
    assert len(lines) == 2 and json.loads(lines[0])["trial_id"] == rec1["trial_id"]
    # superseded trials are still counted
    T.supersede(rec1["trial_id"], rec2["trial_id"], led)
    assert T.n_all(led) == 2
    assert [t for t in T.load_trials(led) if t["trial_id"] == rec1["trial_id"]][0]["superseded_by"] == rec2["trial_id"]
    for f in ("sr", "skew", "kurt", "n_obs", "git_sha", "dirty", "config_hash", "returns_path"):
        assert f in rec1


def test_decorator_logs_before_return(tmp_path, monkeypatch):
    monkeypatch.setattr(T, "LEDGER", tmp_path / "t.jsonl")
    monkeypatch.setattr(T, "RUNS", tmp_path / "runs")

    @T.trial("signal")
    def run():
        return {"params": {"a": 1}, "window": ("2017-01-02", "2024-10-31"), "freq": "W", "returns": rets()}

    out = run()
    assert (tmp_path / "t.jsonl").exists() and T.n_all(tmp_path / "t.jsonl") == 1
    assert out["trial"]["trial_id"]
