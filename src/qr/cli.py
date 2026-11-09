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


if __name__ == "__main__":
    app()
