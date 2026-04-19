import typer

app = typer.Typer(
    help="Teaching-oriented CLI simulator for cross-border payment routing.",
    no_args_is_help=True,
)


@app.callback()
def main() -> None:
    """payment-router command line entrypoint."""
