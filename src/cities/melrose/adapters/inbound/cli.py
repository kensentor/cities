"""The `cities melrose` subcommands: parse arguments, call one use case, print what it found.

Exit codes: 0 success; 1 some documents were quarantined (the rest still loaded); 2 a network or
HTTP failure (nothing written); 3 a local storage failure, or stored state that cannot be exported.
"""

from __future__ import annotations

import argparse
import random
from collections import Counter
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from datetime import date
from typing import TextIO

from cities.melrose.domain.public import ExportSummary
from cities.melrose.domain.reports import NoticeKind, PlacementSummary, RunReport
from cities.melrose.ports.inbound import (
    CollectLogs,
    ExportMap,
    ExportRefused,
    FetchReference,
    RebuildFromArchive,
    SamplePlacements,
)
from cities.melrose.ports.outbound import LogSourceUnavailable, ReferenceSourceUnavailable, StorageFailed

EXIT_OK, EXIT_QUARANTINED, EXIT_NETWORK, EXIT_STORAGE = 0, 1, 2, 3


@dataclass(frozen=True, slots=True)
class UseCases:
    """Factories for each use case; each opens what it needs and closes it on exit."""

    collect: Callable[[], AbstractContextManager[CollectLogs]]
    rebuild: Callable[[], AbstractContextManager[RebuildFromArchive]]
    fetch_reference: Callable[[], AbstractContextManager[FetchReference]]
    sample: Callable[[], AbstractContextManager[SamplePlacements]]
    export: Callable[[], AbstractContextManager[ExportMap]]


def run(argv: Sequence[str], use_cases: UseCases, out: TextIO) -> int:
    args = _parser().parse_args(argv)
    try:
        match args.command:
            case "collect":
                with use_cases.collect() as service:
                    return _print_run(service.collect(since=args.since), out)
            case "rebuild":
                with use_cases.rebuild() as service:
                    return _print_run(service.rebuild(), out, boundary=True)
            case "export":
                with use_cases.export() as service:
                    print(_export_line(service.export()), file=out)
                return EXIT_OK
            case "sample":
                seed = args.seed if args.seed is not None else random.SystemRandom().randrange(10**6)
                with use_cases.sample() as service:
                    picked = service.sample(args.n, seed, call_types=args.type or ())
                print(f"{len(picked)} placed entries, seed {seed}", file=out)
                for version, placement in picked:
                    assert placement.point is not None
                    lat, lon = placement.point.lat, placement.point.lon
                    print(f"\n{version.call_number}  {version.date}  {version.call_type}", file=out)
                    print(f"  published: {version.location_prefix}: {version.location_raw}", file=out)
                    print(f"  placed:    {placement.address_display}  ({placement.kind.value}; {placement.method})", file=out)
                    print(f"  wards:     {', '.join(placement.wards)}", file=out)
                    print(f"  https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map=19/{lat}/{lon}", file=out)
                return EXIT_OK
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
    except ExportRefused as exc:
        print(f"export refused: {exc}", file=out)
        return EXIT_STORAGE


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="cities melrose", description="Melrose, MA police dispatch logs")
    commands = parser.add_subparsers(dest="command", required=True)
    collect = commands.add_parser("collect", help="download new logs and load their entries")
    collect.add_argument("--since", type=date.fromisoformat, default=None, help="earliest upload date (YYYY-MM-DD)")
    commands.add_parser("rebuild", help="re-read every archived log and derive everything again")
    commands.add_parser("export", help="write the map page's data again, after a change to categories.toml")
    commands.add_parser("fetch-reference", help="replace the snapshot of the reference layers")
    sample = commands.add_parser("sample", help="print random placed entries to check against a map")
    sample.add_argument("--n", type=int, default=20)
    sample.add_argument("--seed", type=int, default=None, help="repeat an earlier sample")
    sample.add_argument("--type", action="append", help="only this call type; repeat for several")
    return parser


def _print_run(report: RunReport, out: TextIO, *, boundary: bool = False) -> int:
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
            if notice.kind in (
                NoticeKind.UNNUMBERED_ENTRY,
                NoticeKind.INFERRED_CALL_NUMBER,
                NoticeKind.TRAILING_LOCATION,
                NoticeKind.STRAY_LINE,
            ):
                first_line = notice.text.splitlines()[0] if notice.text else ""
                line(f"  {notice.media_id} {notice.call_number or '(no call number)'} {notice.kind.value}: {first_line}")
    if report.placement is not None:
        _print_placement(report.placement, line, boundary=boundary or report.wrote)
    if report.exported is not None:
        line(_export_line(report.exported))
    return EXIT_QUARANTINED if report.quarantined else EXIT_OK


def _print_placement(summary: PlacementSummary, line: Callable[[str], None], *, boundary: bool) -> None:
    counts = ", ".join(f"{n} {kind}" for kind, n in summary.counts)
    line(f"Placement against reference {summary.reference_version}: {counts}")
    rate = summary.stop_rate
    if rate is not None:
        line(f"Stops placed: {summary.stops_placed} of {summary.stops_placeable} with a location to place ({rate:.1%})")
    for call_number, why in summary.unplaced_stops:
        line(f"  stop not placed: {call_number} {why}")
    if summary.unknown_streets:
        line("Unknown streets: " + ", ".join(f"{name} ({n})" for name, n in summary.unknown_streets))
    if boundary and summary.boundary:
        line("Boundary streets (rule 5): street, ward pair, placed entries near the edge, counted toward both wards")
        for row in summary.boundary:
            line(f"  {row.street:<24} {'/'.join(row.wards):<4} near {row.near:>3}  counted {row.counted:>3}")


def _export_line(summary: ExportSummary) -> str:
    counts = ", ".join(f"{n} {label}" for label, n in summary.counts)
    return f"Map export: {summary.records} records ({counts}), reference {summary.reference_version}"


def _listing(line: Callable[[str], None], title: str, items: Sequence[str]) -> None:
    if items:
        line(f"{title} ({len(items)}): {', '.join(items)}")
