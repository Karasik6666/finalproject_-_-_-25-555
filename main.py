from __future__ import annotations

from valutatrade_hub.cli.interface import main_cli
from valutatrade_hub.logging_config import setup_logging


def main() -> None:
    setup_logging()
    main_cli()


if __name__ == "__main__":
    main()