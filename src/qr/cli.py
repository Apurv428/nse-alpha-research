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


if __name__ == "__main__":
    app()
