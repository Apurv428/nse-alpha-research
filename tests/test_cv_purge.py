"""PRD section 7 assertions, for every fold (and the inner split)."""
import datetime as dt

import numpy as np
import polars as pl
import pytest

from qr.models import cv


def dev_calendar():
    d, out = dt.date(2013, 2, 1), []
    while d <= dt.date(2024, 10, 31):
        if d.weekday() < 5:
            out.append(d)
        d += dt.timedelta(days=1)
    return pl.DataFrame({"trade_date": out, "sess": list(range(len(out)))}, schema_overrides={"sess": pl.Int64})


CAL = dev_calendar()
FOLDS = cv.make_folds(CAL)
S = dict(zip(CAL["trade_date"], CAL["sess"]))


def label_end_sess(t_sess, h=5):
    return t_sess + 1 + h


def test_eight_folds():
    assert FOLDS.height == 8 and FOLDS["fold_id"].to_list() == list(range(1, 9))


@pytest.mark.parametrize("k", range(8))
def test_max_train_label_end_before_test_start(k):
    f = FOLDS.row(k, named=True)
    ts = cv.train_sessions(CAL, f)
    assert label_end_sess(ts.max()) < S[f["test_start"]]


@pytest.mark.parametrize("k", range(8))
def test_gap_at_least_27_sessions(k):
    f = FOLDS.row(k, named=True)
    ts = cv.train_sessions(CAL, f)
    assert S[f["test_start"]] - ts.max() >= 27
    assert S[f["test_start"]] - S[f["train_end"]] == 27


def test_test_folds_tile_the_window_without_gaps_or_overlaps():
    cal_dates = CAL["trade_date"].to_list()
    prev_end = None
    covered = []
    for f in FOLDS.iter_rows(named=True):
        if prev_end is not None:
            assert S[f["test_start"]] == S[prev_end] + 1  # next session: no gap, no overlap
        prev_end = f["test_end"]
        covered += [d for d in cal_dates if f["test_start"] <= d <= f["test_end"]]
    assert covered == sorted(set(covered))
    assert FOLDS["test_start"][0] == dt.date(2017, 1, 2) and FOLDS["test_end"][-1] == dt.date(2024, 10, 31)


def test_no_date_after_dev_end_anywhere():
    dev_end = dt.date(2024, 10, 31)
    for f in FOLDS.iter_rows(named=True):
        assert max(f["train_end"], f["test_end"], f["test_start"]) <= dev_end
        assert cv.train_sessions(CAL, f).max() <= S[f["train_end"]]


def test_training_is_every_fifth_date_and_expanding():
    n = [len(cv.train_sessions(CAL, f)) for f in FOLDS.iter_rows(named=True)]
    assert n == sorted(n) and n[0] > 100
    ts = cv.train_sessions(CAL, FOLDS.row(0, named=True))
    assert (np.diff(ts) == 5).all()


def test_inner_split_is_purged_and_embargoed():
    for f in FOLDS.iter_rows(named=True):
        ts = cv.train_sessions(CAL, f)
        inner, val = cv.inner_split(ts)
        assert len(val) == pytest.approx(0.2 * len(ts), abs=1)
        assert val[0] - inner.max() >= 27 and label_end_sess(inner.max()) < val[0]
