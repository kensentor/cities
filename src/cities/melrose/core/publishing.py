"""What leaves SQLite for the map page, and in what form (design R4, R9, R10; technical spec T14)."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from datetime import datetime

from cities.melrose.core import rules
from cities.melrose.domain.entries import EntryState, EntryVersion
from cities.melrose.domain.logs import DocumentRecord
from cities.melrose.domain.places import Placement, PlacementKind
from cities.melrose.domain.public import (
    Category,
    ExportSummary,
    PublicDocument,
    PublicExport,
    PublicRecord,
    WardOutline,
)
from cities.melrose.domain.vocabulary import ARREST_RESULT, KNOWN_RESULTS, TRUNCATED_RESULTS
from cities.melrose.ports.inbound import ExportRefused
from cities.melrose.ports.outbound import Clock, EntryRepository, Gazetteer, MapPublisher

ARREST = "Arrest"
PLACED = (PlacementKind.ADDRESS, PlacementKind.INTERSECTION)

# A result printed cut short is shown as its full form when exactly one known result completes it
# (A10), so a result filter catches it; "False Alarm/Cancelled Alarm Co" has none and stays as printed.
# Arrests are matched by pattern rather than listed, so "* Arrest" stands in for them here: "*" could be
# an arrest or "* Report taken", and stays as printed.
_COMPLETIONS: dict[str, str] = {
    cut: full[0]
    for cut in TRUNCATED_RESULTS
    if len(full := sorted(k for k in KNOWN_RESULTS | {"* Arrest"} if k.startswith(cut + " "))) == 1
}


def public_result(result: str) -> str:
    """Any arrest result is "Arrest", because sex and age band could identify a person (A2)."""
    if ARREST_RESULT.fullmatch(result):
        return ARREST
    return _COMPLETIONS.get(result, result)


def build_export(
    documents: Sequence[DocumentRecord],
    states: Sequence[EntryState],
    versions: Sequence[EntryVersion],
    placements: Sequence[Placement],
    categories: Sequence[Category],
    wards: Sequence[WardOutline],
    reference_version: str,
    generated_at: datetime,
) -> PublicExport:
    """Current entries of the listed call types, with only the fields the page may show."""
    category_of = {t: c.key for c in categories for t in c.call_types}
    shown = sorted(
        (v for v in rules.current_versions(states, versions) if v.call_type in category_of),
        key=lambda v: (v.date, v.time, v.call_number),
    )
    placed = {p.call_number: p for p in placements}
    missing = [v.call_number for v in shown if v.call_number not in placed]
    if missing:
        raise ExportRefused(f"{len(missing)} entries to show have no placement (e.g. {missing[0]}); run rebuild")
    stale = sorted({placed[v.call_number].reference_version for v in shown} - {reference_version})
    if stale:
        raise ExportRefused(
            f"placements use reference {', '.join(stale)} but the snapshot is {reference_version}; run rebuild"
        )
    by_id = {d.media_id: d for d in documents}
    used = sorted({v.document_id for v in shown})
    index = {media_id: i for i, media_id in enumerate(used)}
    public_documents = tuple(_document(by_id[media_id]) for media_id in used)
    records = tuple(_record(v, placed[v.call_number], category_of[v.call_type], index[v.document_id]) for v in shown)
    return PublicExport(
        generated_at=generated_at,
        reference_version=reference_version,
        categories=tuple(categories),
        documents=public_documents,
        records=records,
        wards=tuple(wards),
    )


def _document(record: DocumentRecord) -> PublicDocument:
    assert record.first_date is not None and record.last_date is not None, "a loaded log has dates"
    return PublicDocument(record.archived.log.source_url, record.first_date, record.last_date)


def _record(v: EntryVersion, p: Placement, category: str, doc: int) -> PublicRecord:
    on_map = p.kind in PLACED
    return PublicRecord(
        call=v.call_number,
        date=v.date,
        time=v.time,
        category=category,
        call_type=v.call_type,
        result=public_result(v.result),
        # Only the rebuilt address, and only for a placed entry, ever leaves (design R10).
        address=p.address_display if on_map else None,
        vicinity=v.location_prefix == "Vicinity of",
        kind=p.kind,
        point=p.point if on_map else None,
        # An entry outside Melrose counts toward no Melrose street.
        streets=() if p.kind is PlacementKind.OUTSIDE else p.streets,
        wards=p.wards if on_map else (),
        doc=doc,
        page=v.page,
    )


def summarise(export: PublicExport) -> ExportSummary:
    counts = Counter(r.category for r in export.records)
    return ExportSummary(export.reference_version, tuple((c.label, counts[c.key]) for c in export.categories))


def publish_map(
    repository: EntryRepository,
    gazetteer: Gazetteer,
    publisher: MapPublisher,
    categories: Sequence[Category],
    clock: Clock,
) -> ExportSummary:
    export = build_export(
        repository.documents(),
        repository.entries(),
        repository.versions(),
        repository.placements(),
        categories,
        gazetteer.ward_outlines(),
        gazetteer.reference_version(),
        clock.now(),
    )
    publisher.publish(export)
    return summarise(export)
