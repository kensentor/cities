"""The `cities` command: one subcommand group per city."""

from __future__ import annotations

import sys
from collections.abc import Sequence

from cities.melrose import handler as melrose

CITIES = {"melrose": melrose.main}


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] not in CITIES:
        print(f"usage: cities {{{','.join(CITIES)}}} COMMAND ...", file=sys.stderr)
        return 2
    return CITIES[args[0]](args[1:])


if __name__ == "__main__":
    raise SystemExit(main())
