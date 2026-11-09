import numpy as np
import polars as pl
import pytest

from qr.eval.neutralize import neutralize_one_date, winsor_z


def test_neutral_score_is_orthogonal_to_size_beta_and_has_zero_sector_means():
    rng = np.random.default_rng(0)
    n = 600
    sector = rng.choice(["A", "B", "C", "D"], n)
    size, beta = rng.normal(size=n), rng.normal(1, 0.3, n)
    z = 2.0 * size - 1.5 * beta + (sector == "A") * 1.0 + (sector == "C") * -2.0 + rng.normal(size=n)
    zn = neutralize_one_date(z, sector, beta, size)
    assert abs(np.corrcoef(zn, size)[0, 1]) < 1e-10 and abs(np.corrcoef(zn, beta)[0, 1]) < 1e-10
    for s in "ABCD":
        assert abs(zn[sector == s].mean()) < 1e-10
    assert zn.mean() == pytest.approx(0, abs=1e-12) and zn.std(ddof=1) == pytest.approx(1.0)


def test_small_sectors_merge_into_unclassified():
    rng = np.random.default_rng(1)
    n = 200
    sector = np.array(["Big"] * 150 + ["Unclassified"] * 46 + ["Tiny1"] * 2 + ["Tiny2"] * 2, dtype=object)
    z = rng.normal(size=n) + (sector == "Tiny1") * 5.0  # a 2-name sector's shift must NOT be absorbed by its own dummy
    zn = neutralize_one_date(z, sector, np.ones(n), rng.normal(size=n))
    assert zn[sector == "Tiny1"].mean() > 1.0


def test_winsor_z_clips_outliers_and_standardizes_per_date():
    rng = np.random.default_rng(2)
    n = 1000
    raw = rng.normal(size=n)
    raw[0] = 1e6
    df = pl.DataFrame({"trade_date": [1] * n, "sid": list(range(n)), "signal": ["S"] * n, "raw": raw})
    out = winsor_z(df)
    assert out["z"].mean() == pytest.approx(0, abs=1e-9) and out["z"].std() == pytest.approx(1.0)
    assert out["z"].max() < 5  # the 1e6 print was clipped to the 99th percentile
