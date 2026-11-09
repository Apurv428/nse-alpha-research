"""OOS refusal paths (tmp git repo + tmp lock) and the freeze/score mechanics on synthetic gold."""
import hashlib
import json
import subprocess

import numpy as np
import polars as pl
import pytest

from qr import oos as O
from qr.guard import oos_lock as L
from qr.models import freeze as F

from test_models import make_gold


def git(repo, *a):
    subprocess.run(["git", *a], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def world(tmp_path):
    repo = tmp_path / "repo"
    (repo / "frozen").mkdir(parents=True)
    git(repo, "init", "-q"); git(repo, "config", "user.email", "t@t"); git(repo, "config", "user.name", "t")
    (repo / "frozen" / "frozen.json").write_text('{"model": "EW"}')
    lock = repo / "oos.lock"
    L.seal(lock)
    L.set_headline("EW", {"frozen_sha256": hashlib.sha256((repo / "frozen" / "frozen.json").read_bytes()).hexdigest()}, lock)
    git(repo, "add", "-A"); git(repo, "commit", "-qm", "c")
    git(repo, "tag", "oos-candidate")
    return repo, lock, repo / "frozen"


def test_preconditions_pass_then_each_failure_refuses(world):
    repo, lock, fz = world
    assert O.check_preconditions(lock, fz, repo)["state"] == "sealed"
    (repo / "x.txt").write_text("dirty")
    with pytest.raises(L.OOSLockError, match="not clean"):
        O.check_preconditions(lock, fz, repo)
    git(repo, "add", "-A"); git(repo, "commit", "-qm", "d")                      # clean again, but HEAD no longer tagged
    with pytest.raises(L.OOSLockError, match="oos-candidate"):
        O.check_preconditions(lock, fz, repo)
    git(repo, "tag", "-f", "oos-candidate")
    (fz / "frozen.json").write_text('{"model": "RIDGE"}')
    git(repo, "add", "-A"); git(repo, "commit", "-qm", "e"); git(repo, "tag", "-f", "oos-candidate")
    with pytest.raises(L.OOSLockError, match="hash"):
        O.check_preconditions(lock, fz, repo)


def test_second_open_and_missing_confirm_are_refused(world):
    repo, lock, fz = world
    with pytest.raises(L.OOSLockError, match="--confirm"):
        O.run_oos(False)
    L.mark_opened("abc", lock)
    with pytest.raises(L.OOSLockError, match="already"):
        O.check_preconditions(lock, fz, repo)
    L.mark_read("h", lock)
    with pytest.raises(L.OOSLockError, match="already"):
        O.check_preconditions(lock, fz, repo)


def test_freeze_ridge_and_lgbm_roundtrip_and_scores_are_standardized(tmp_path):
    make_gold(tmp_path, planted=True, ns=40)
    sig = pl.read_parquet(tmp_path / "gold" / "signals" / "signals.parquet")
    fwd = pl.read_parquet(tmp_path / "gold" / "fwd_returns" / "fwd_returns.parquet")
    ctx = pl.read_parquet(tmp_path / "gold" / "context" / "context.parquet")
    cal = pl.read_parquet(tmp_path / "silver" / "calendar" / "calendar.parquet")
    for model in ("RIDGE", "LGBM", "EW"):
        meta = F.fit_final(sig, fwd, ctx, cal, model, tmp_path / f"fz_{model}")
        assert meta["model"] == model
        fz = F.load_frozen(tmp_path / f"fz_{model}")
        from qr.models.run import wide_features
        X, _ = wide_features(sig, ctx)
        s = F.score(fz, X)
        g = s.group_by("trade_date").agg(m=pl.col("score").mean(), sd=pl.col("score").std())
        assert g["m"].abs().max() < 1e-9 and (g["sd"] - 1).abs().max() < 1e-9
        if model == "RIDGE":
            assert meta["coef"][0] > 0 and meta["coef"][1] > 0 and meta["train_end"] < "2024-10-31"
    # the train window ends GAP sessions before the first OOS session
    assert meta["model"] == "EW"
