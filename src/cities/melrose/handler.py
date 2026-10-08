"""Entry point for `cities melrose`: read the settings, wire the use cases, run the command."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from functools import partial

from cities.melrose import composition
from cities.melrose.adapters.inbound import cli
from cities.melrose.settings import load_settings


def main(argv: Sequence[str]) -> int:
    settings = load_settings()
    use_cases = cli.UseCases(
        collect=partial(composition.collect_logs, settings),
        rebuild=partial(composition.rebuild_from_archive, settings),
        fetch_reference=partial(composition.fetch_reference, settings),
    )
    return cli.run(argv, use_cases, sys.stdout)
