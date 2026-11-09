"""`qr` command line. Stages are added day by day (PRD section 2)."""
import typer

app = typer.Typer(help="NSE cross-sectional alpha research pipeline", no_args_is_help=True)


@app.callback()
def main() -> None:
    """NSE cross-sectional alpha research pipeline."""


@app.command()
def version() -> None:
    """Print the package version."""
    from importlib.metadata import version as v

    typer.echo(v("nse-alpha-research"))


@app.command()
def ingest(
    start: str = typer.Option("2012-01-02"),
    end: str = typer.Option("2026-10-30"),
    root: str = typer.Option("data/raw"),
) -> None:
    """Download raw NSE archives (cached, 1 req/s). Resumable; stops on 403/429."""
    import datetime as dt
    from pathlib import Path

    from qr.ingest.download import run

    counts = run(dt.date.fromisoformat(start), dt.date.fromisoformat(end), Path(root))
    typer.echo(counts)


@app.command()
def bronze(table: str = typer.Argument("all")) -> None:
    """Parse raw files into bronze parquet (one table per source). Idempotent."""
    from qr.ingest.bronze import SOURCES, build

    for t in (SOURCES if table == "all" else [table]):
        m = build(t)
        typer.echo(f"{t}: {m['n_input_files']} files, rows/year {m['rows_per_year']}")


@app.command()
def panel() -> None:
    """Build silver (security master, adjusted prices, universe, futures, bench, sectors) and data-QA outputs."""
    import json

    from qr.panel.build import build_silver

    typer.echo(json.dumps(build_silver(), indent=1, default=str))


@app.command()
def qa() -> None:
    """Day 1 gate checks -> runs/data_qa/gate_report.json."""
    import json

    from qr.panel.qa import run_qa

    typer.echo(json.dumps(run_qa(), indent=1, default=str))


@app.command()
def signals() -> None:
    """Build gold (signals raw/z/z_neu, forward returns, context). Dev window only while the lock is sealed."""
    import json

    from qr.signals.gold import build_gold

    typer.echo(json.dumps(build_gold(), indent=1))


@app.command()
def eval() -> None:  # noqa: A001
    """Single-signal evaluation (logged as trials before printing)."""
    import json

    from qr.eval.run import run_eval

    res = run_eval()
    if res["sig.tripwire_hit"]:
        typer.echo("TRIPWIRE: a signal has mean rank IC > 0.08 at h=5. STOP and run a leakage audit (PRD s11).", err=True)
    typer.echo(json.dumps({k: v for k, v in res.items() if k != "trial_ids"}, indent=1, default=str))


@app.command()
def fit() -> None:
    """Walk-forward combiners EW / ridge / LightGBM (24 trials logged) and the selection rule."""
    import json

    from qr.models.run import run_combine

    res = run_combine()
    typer.echo(json.dumps({k: v for k, v in res.items() if k not in ("combo.trial_ids", "selection")}, indent=1, default=str))
    typer.echo("selection: " + json.dumps(res["selection"], default=str))


@app.command()
def backtest() -> None:
    """P0/P1/P2 gross and net on the development window, costs, capacity, sensitivities (2 trials logged)."""
    import json

    from qr.portfolio.run import run_books

    res = run_books()
    if res.get("p1.dev.tripwire"):
        typer.echo("TRIPWIRE: P1 net IR > 2.0 on the development window. STOP and audit for leakage (PRD s11).", err=True)
    typer.echo(json.dumps(res, indent=1, default=str))


if __name__ == "__main__":
    app()
