"""Allow ``python -m payment_router`` to run the CLI."""

from payment_router.cli import app

if __name__ == "__main__":
    app()
