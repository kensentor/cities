# cities

A map of where police in Melrose, MA make traffic stops, built from the department's published weekly dispatch logs. The design and technical specs are in [docs/specs/traffic-stops-map/](docs/specs/traffic-stops-map/).

Phase 1 is built: collecting the logs, keeping each one as published, and loading its entries into SQLite. Placement on the map (phase 2) and the map page (phase 3) are not built yet.

## Setup

Python 3.14 and [uv](https://docs.astral.sh/uv/).

```sh
uv sync
```

## Commands

Run each command from the repo root. Data goes to `data/melrose/` unless `CITIES_DATA_DIR` names another root.

| Command | What it does |
|---|---|
| `uv run cities melrose collect [--since YYYY-MM-DD]` | Lists the logs uploaded since 2026-07-20, downloads any not seen before, keeps each PDF, and loads its entries. Running it again with nothing new writes nothing. |
| `uv run cities melrose rebuild` | Re-reads every archived PDF and derives everything again. Use it after a parser change, on a fresh clone, or after putting hand-downloaded PDFs in the archive. |
| `uv run cities melrose fetch-reference` | Replaces the snapshot of the MassGIS address points, MassDOT roads and MassGIS wards. If any layer comes back short, the old snapshot stays. |

Exit codes: 0 success; 1 some logs were quarantined, though the rest loaded; 2 a network or HTTP failure, with nothing written; 3 a local storage failure.

After a `collect` that found new logs, commit the new files in `data/melrose/raw/` and push. Until then they exist only on this machine.

## What a run reports

A quarantined log printed the reason it could not be loaded, such as an unknown result or a call-number count that does not match. Fix the line rules in `adapters/outbound/log_grammar.py`, or add the result to `domain/vocabulary.py`, with a test that reproduces it, then run `rebuild`.

Some damage in the published logs cannot be fixed by a parser, so it is loaded anyway and reported as a notice:

- **inferred call number**: an entry printed without its call number, stored under the call its own `Refer To` line names. Its `raw_block` holds that line.
- **unnumbered entry**: an entry printed without its call number and with no `Refer To` line to take one from, or one naming a call printed elsewhere in the log. It has no key to store it under, so it is reported and not stored.
- **trailing location**: a location line after an entry's first location, or after its `ID:`, `Refer To` or `Charges:` lines. It is usually left behind when the department withholds the entry that owned it. It stays in `raw_block` and never becomes the entry's location.
- **leftover line**: a line that continues nothing, such as `:` or the tail of a removed line.
- **truncated result**: a result printed cut short, such as "Taken/Referred to Other", stored as printed.

A call type not listed in `src/cities/melrose/call_types.txt` is reported every run until you add it there.

## Layout

The Python package is built as ports and adapters (technical spec T16). The counting, versioning and privacy rules live in a core that imports no PDF, HTTP, database or logging library.

```
src/cities/cli.py                       `cities` command; dispatches to one handler per city
src/cities/melrose/
  domain/                               stdlib types; vocabulary.py holds the known results
  ports/inbound.py, ports/outbound.py   the use cases, and what the core drives
  core/                                 collect | rebuild | reference, over loading, over rules
  adapters/inbound/cli.py               argument parsing and the printed report
  adapters/outbound/                    wordpress, pdf_reader + log_grammar, log_archive, sqlite_repo, arcgis, reference_files, clock
  stubs.py                              in-memory fakes of every outbound port
  settings.py                           data paths, the start date, the reference layers, call_types.txt
  composition.py                        the only place adapters are built
  handler.py                            `cities melrose` entry point
data/melrose/raw/                       committed: each PDF as <sha256>.pdf, plus <media id>.json saying which upload it was
data/melrose/reference/                 committed: one GeoJSON file per layer, plus manifest.json
data/melrose/db.sqlite                  git-ignored; `rebuild` recreates it
tests/melrose/                          pytest
```

| Outbound port | Adapter |
|---|---|
| `LogSource`: find and fetch published logs | the site's WordPress media API, 2 s between requests |
| `LogReader`: read the entries in a log | pdfplumber lines, through the line grammar |
| `LogArchive`: keep each log as downloaded | files in `data/melrose/raw/` |
| `EntryRepository`: documents, versions, current entries, runs | SQLite |
| `ReferenceSource`: fetch reference layers | ArcGIS REST |
| `ReferenceStore`: keep the reference snapshot | GeoJSON files in `data/melrose/reference/` |
| `Clock` | the system clock |

## Checks

```sh
uv run pytest
uv run pyright
uv run lint-imports
```

The import contracts and the pyright settings are in `pyproject.toml`. pyright runs in `standard` mode, because only `standard` reports an adapter whose signature drifted from its port. Each contract was proven on 2026-10-07 by planting a violation it forbids and seeing exactly that contract report BROKEN. Repeat that after changing a contract.

These tests guard rules that would otherwise fail without any error:

| Invariant | Test |
|---|---|
| The current version is the latest upload covering the entry's date; an entry missing from it is withdrawn | `test_rules.py::test_current_version_is_the_latest_upload_covering_the_entry_date`, `::test_an_entry_missing_from_the_latest_covering_log_is_withdrawn` |
| A withheld entry's location never becomes another entry's location | `test_rules.py::test_trailing_location_never_becomes_the_entry_location`, `test_published_logs.py::test_a_withheld_entrys_location_left_after_an_arrest_is_not_this_entrys` |
| A line that would have fitted on the line before is not joined to it | `test_log_grammar.py::test_a_word_that_would_have_fitted_is_not_a_wrap`, `test_published_logs.py::test_text_after_page_furniture_that_would_have_fitted_is_not_a_location` |
| Every call number printed in a log becomes exactly one stored entry | `test_published_logs.py::test_every_log_since_jul_20_passes_the_completeness_check` |
| Collecting again changes nothing, and `rebuild` equals incremental collection | `test_use_cases.py::test_collecting_again_writes_nothing`, `::test_rebuild_from_the_archive_equals_incremental_collection` |
| A failed download writes nothing | `test_use_cases.py::test_a_failed_download_writes_nothing` |
| Every adapter inherits its port, and every port method is abstract | `test_ports.py` |
