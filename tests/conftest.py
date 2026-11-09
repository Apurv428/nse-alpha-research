"""Deterministic numerics for the test-suite: the PIT truncation tests assert BIT-identical values, and multi-threaded
float reductions (Polars group-bys, BLAS) are not run-to-run deterministic at the 1e-15 level (DECISIONS D-016)."""
import os

for k in ("POLARS_MAX_THREADS", "OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(k, "1")
