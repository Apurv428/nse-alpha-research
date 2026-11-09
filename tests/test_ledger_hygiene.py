"""RESULTS.md numbers come only from run files; the report may only show results via \\res{id}."""
import csv
import json
import re
from pathlib import Path

from qr.report import ledger as R

ROOT = Path(__file__).resolve().parents[1]


def test_missing_files_print_not_run_and_present_values_trace(tmp_path):
    runs = tmp_path / "runs"
    (runs / "combo_20250101T000000").mkdir(parents=True)
    (runs / "combo_20250101T000000" / "metrics.json").write_text(json.dumps({"combo.headline": "EW", "combo.ew.rank_ic": 0.0123456}))
    (runs / "oos").mkdir()
    with (runs / "oos" / "costs.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, ["book", "drag_bp_pa_stt", "drag_bp_pa_spread"]); w.writeheader(); w.writerow({"book": "P1", "drag_bp_pa_stt": 30, "drag_bp_pa_spread": 10})
    rows = {r["id"]: r for r in R.collect(runs)}
    assert rows["combo.headline"]["text"] == "EW" and rows["combo.ew.rank_ic"]["text"] == "0.012"
    assert rows["combo.headline.rank_ic"]["text"] == "not run"                  # key absent -> not run, never an estimate
    assert rows["sig.best_neu.name"]["text"] == "not run"                       # no eval run at all
    assert rows["p1.oos.cost_drag_bp"]["value"] == 40 and rows["p1.oos.stt_share_pct"]["value"] == 75.0
    assert "combo_20250101T000000/metrics.json" in rows["combo.headline"]["source"]
    out = R.write_all(runs, tmp_path / "RESULTS.md", tmp_path / "numbers.tex")
    assert out["n_not_run"] > 0 and "not run" in (tmp_path / "numbers.tex").read_text()


def test_report_and_readme_use_only_registered_result_ids():
    ids = set(R.IDS)
    for p in list((ROOT / "report").glob("**/*.tex")) + [ROOT / "README.md"]:
        if p.name == "numbers.tex" or not p.exists():
            continue
        for m in re.findall(r"\\res\{([^}]+)\}", p.read_text()):
            assert m in ids, f"{p.name}: unknown result id {m}"
