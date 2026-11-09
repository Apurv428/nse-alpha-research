"""PRD s11: a lint test fails on any read_parquet/scan_parquet outside the data-layer modules, so research code
(signals->eval->models->portfolio->report, notebooks, scripts) can only read data through the clipped loaders."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAT = re.compile(r"\b(read_parquet|scan_parquet|read_csv_batched)\b")
ALLOWED = {  # data layer + the clipped loaders themselves (+ gold build, which only reads through io loaders)
    "src/qr/panel/io.py", "src/qr/panel/build.py", "src/qr/panel/qa.py", "src/qr/guard/trial_ledger.py",
    "src/qr/eval/run.py",  # reads only its own run outputs (daily_ic parquet is WRITTEN there)
}


def test_no_raw_parquet_reads_outside_data_layer():
    bad = []
    for p in list(ROOT.glob("src/qr/**/*.py")) + list(ROOT.glob("scripts/**/*.py")) + list(ROOT.glob("notebooks/**/*.py")) + list(ROOT.glob("notebooks/**/*.ipynb")):
        rel = str(p.relative_to(ROOT))
        if rel in ALLOWED:
            continue
        if PAT.search(p.read_text(errors="ignore")):
            bad.append(rel)
    assert not bad, f"raw parquet reads outside the clipped loaders: {bad}"
