"""Environment smoke test: pinned stack imports and the CLI loads."""
import sys

import pytest
from typer.testing import CliRunner


def test_python_version():
    assert sys.version_info[:2] == (3, 11)


def test_stack_imports():
    import duckdb, hypothesis, lightgbm, mlflow, numpy, polars, pyarrow  # noqa: F401
    import scipy, sklearn, statsmodels, yaml  # noqa: F401


def test_cli_runs():
    from qr.cli import app

    r = CliRunner().invoke(app, ["version"])
    assert r.exit_code == 0 and r.stdout.strip()


def test_polars_hac_roundtrip():
    import numpy as np
    import polars as pl
    import statsmodels.api as sm

    x = np.random.default_rng(0).normal(size=200)
    res = sm.OLS(x, np.ones_like(x)).fit(cov_type="HAC", cov_kwds={"maxlags": 4})
    assert np.isfinite(res.tvalues[0])
    assert pl.DataFrame({"x": x}).select(pl.col("x").mean()).item() == pytest.approx(float(x.mean()), abs=1e-12)
