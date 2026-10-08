"""The `cities melrose` subcommands: parse arguments, call one use case, print what it found.

Exit codes: 0 success; 1 some documents were quarantined (the rest still loaded); 2 a network or
HTTP failure (nothing written); 3 a local storage failure.
"""

from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import date
from typing import TextIO

from cities.melrose.domain.reports import NoticeKind, RunReport
from cities.melrose.ports.inbound import CollectLogs, FetchReference, RebuildFromArchive
from cities.melrose.ports.outbound import LogSourceUnavailable, ReferenceSourceUnavailable, StorageFailed

EXIT_OK, EXIT_QUARANTINED, EXIT_NETWORK, EXIT_STORAGE = 0, 1, 2, 3


@dataclass(frozen=True, slots=True)
class UseCases:
    """Factories for each use case; each opens what it needs and closes it on exit."""

    collect: Callable[[], AbstractContextManager[CollectLogs]]
    rebuild: Callable[[], AbstractContextManager[RebuildFromArchive]]
    fetch_reference: Callable[[], AbstractContextManager[FetchReference]]


def run(argv: Sequence[str], use_cases: UseCases, out: TextIO) -> int:
    args = _parser().parse_args(argv)
    try:
        match args.command:
            case "collect":
                with use_cases.collect() as service:
                    return _print_run(service.collect(since=args.since), out)
            case "rebuild":
                with use_cases.rebuild() as service:
                    return _print_run(service.rebuild(), out)
            case _:
                with use_cases.fetch_reference() as service:
                    report = service.fetch_reference()
                for name, count in report.counts:
                    print(f"{name}: {count} features", file=out)
                print(f"reference version {report.reference_version}", file=out)
                return EXIT_OK
    except (LogSourceUnavailable, ReferenceSourceUnavailable) as exc:
        print(f"network failure, nothing written: {exc}", file=out)
        return EXIT_NETWORK
    except StorageFailed as exc:
        print(f"storage failure: {exc}", file=out)
        return EXIT_STORAGE


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cities melrose", description="Melrose, MA police dispatch logs")
    commands = parser.add_subparsers(dest="command", required=True)
    collect = commands.add_parser("collect", help="download new logs and load their entries")
    collect.add_argument("--since", type=date.fromisoformat, default=None, help="earliest upload date (YYYY-MM-DD)")
    commands.add_parser("rebuild", help="re-read every archived log and derive everything again")
    commands.add_parser("fetch-reference", help="replace the snapshot of the reference layers")
    return parser


def _print_run(report: RunReport, out: TextIO) -> int:
    def line(text: str = "") -> None:
        print(text, file=out)

    if not report.wrote:
        line("No new logs; nothing written.")
    for record in report.documents_new:
        log = record.archived.log
        span = f"{record.first_date} to {record.last_date}" if record.first_date else "no dates"
        line(f"{log.media_id} {record.status.value:<12} {span}  {log.title}")
    line(f"Documents: {len(report.documents_new)}   new entries: {report.entries_new}")
    for record in report.quarantined:
        line(f"QUARANTINED {record.media_id}: {record.error}")
    _listing(line, "Call numbers printed twice", report.conflicts)
    _listing(line, "Entries whose versions differ between logs", report.versions_differing)
    _listing(line, "Entries withdrawn", report.withdrawn)
    _listing(line, "Call types not in call_types.txt", report.new_call_types)
    _listing(line, "Dates with no entries", [d.isoformat() for d in report.dates_without_entries])
    if report.notices:
        counts = Counter(n.kind for n in report.notices)
        line("Source damage, loaded anyway: " + ", ".join(f"{counts[k]} {k.value}" for k in NoticeKind if counts[k]))
        for notice in report.notices:
            if notice.kind in (NoticeKind.UNNUMBERED_ENTRY, NoticeKind.TRAILING_LOCATION, NoticeKind.STRAY_LINE):
                first_line = notice.text.splitlines()[0] if notice.text else ""
                line(f"  {notice.media_id} {notice.call_number or '(no call number)'} {notice.kind.value}: {first_line}")
    return EXIT_QUARANTINED if report.quarantined else EXIT_OK


def _listing(line: Callable[[str], None], title: str, items: Sequence[str]) -> None:
    if items:
        line(f"{title} ({len(items)}): {', '.join(items)}")
