# cities

A map of where police in Melrose, MA make traffic stops, built from the department's published weekly dispatch logs. The design and technical specs are in [docs/specs/traffic-stops-map/](docs/specs/traffic-stops-map/).

Phases 1–3 are built: collecting the logs, keeping each one as published, loading its entries into SQLite, placing each entry against an offline snapshot of MassGIS and MassDOT data, exporting the stops and crashes the map may show, and the map page in `site/`.

## Setup

Python 3.14 and [uv](https://docs.astral.sh/uv/) for the collector; Node 22.12 or later for the map page.

```sh
uv sync
cd site && npm install
```

## Commands

Run each command from the repo root. Data goes to `data/melrose/` unless `CITIES_DATA_DIR` names another root.

| Command | What it does |
|---|---|
| `uv run cities melrose collect [--since YYYY-MM-DD]` | Lists the logs uploaded since 2026-07-20, downloads any not seen before, keeps each PDF, loads its entries, and places them. Running it again with nothing new writes nothing. |
| `uv run cities melrose rebuild` | Re-reads every archived PDF and derives everything again, placements included. Use it after a parser change, after `fetch-reference`, on a fresh clone, or after putting hand-downloaded PDFs in the archive. |
| `uv run cities melrose sample [--n 20] [--seed S] [--type CALL TYPE …]` | Prints random placed entries with their published location, the address shown, the method and an OpenStreetMap link, to check by eye that each lies where its log says. The seed is printed, so a sample can be repeated. |
| `uv run cities melrose export` | Writes the map page's data again from what is stored: after editing `categories.toml`, or once for a database built before phase 3, since a `collect` with nothing new writes nothing. `collect` (when it found something) and `rebuild` export too. It refuses, exiting 3, if the placements came from another reference snapshot: run `rebuild` after `fetch-reference`. |
| `uv run cities melrose fetch-reference` | Replaces the snapshot of the MassGIS address points, MassDOT roads and MassGIS wards. If any layer comes back short, the old snapshot stays. |

Exit codes: 0 success; 1 some logs were quarantined, though the rest loaded; 2 a network or HTTP failure, with nothing written; 3 a local storage failure, or stored data that cannot be exported as it is.

After a `collect` that found new logs, commit the new files in `data/melrose/raw/`. Until then they exist only on this machine.

The database records its schema version. A database from an older version is refused with a message to delete `data/melrose/db.sqlite` and run `rebuild`, which recreates everything from the committed archive and snapshot.

## The map page

`src/cities/melrose/categories.toml` decides which call types leave SQLite and how the map groups them: Stops, and Crashes (three call types). Every other call type is stored but never exported. The export goes to `site/public/data/melrose/` (git-ignored; `CITIES_SITE_DATA_DIR` overrides `site/public/data`): `entries.json`, whose shape is the technical spec's Appendix D, and `wards.geojson`.

```sh
cd site
npm run dev        # serve the page at http://localhost:5173
npm test           # vitest on src/aggregate.ts
npm run typecheck
npm run build      # site/dist, a static site including the export
```

The page loads the export once and does all filtering and counting in the browser, in `src/aggregate.ts`, which uses neither Leaflet nor the DOM. Markers and the "not on the map" counts follow every filter. The ward table and street ranking have their own categories, so the Show checkboxes don't apply to them; the date range applies to both of the ward table's columns, and the result filter to stops only (design R6).

What the export may carry is decided in `core/publishing.py`: only current entries of the listed call types; any arrest result as "Arrest"; a result printed cut short as its one full form, where it has one; the address rebuilt from the house number and reference street, and only for an entry on the map. An entry outside Melrose counts toward no street.

## What a run reports

A quarantined log printed the reason it could not be loaded, such as an unknown result or a call-number count that does not match. Fix the line rules in `adapters/outbound/log_grammar.py`, or add the result to `domain/vocabulary.py`, with a test that reproduces it, then run `rebuild`.

Some damage in the published logs cannot be fixed by a parser, so it is loaded anyway and reported as a notice:

- **inferred call number**: an entry printed without its call number, stored under the call its own `Refer To` line names. Its `raw_block` holds that line.
- **unnumbered entry**: an entry printed without its call number and with no `Refer To` line to take one from, or one naming a call printed elsewhere in the log. It has no key to store it under, so it is reported and not stored.
- **trailing location**: a location line after an entry's first location, or after its `ID:`, `Refer To` or `Charges:` lines. It is usually left behind when the department withholds the entry that owned it. It stays in `raw_block` and never becomes the entry's location.
- **leftover line**: a line that continues nothing, such as `:` or the tail of a removed line.
- **truncated result**: a result printed cut short, such as "Taken/Referred to Other", stored as printed.

A call type not listed in `src/cities/melrose/call_types.txt` is reported every run until you add it there.

Every run also reports placement against the reference snapshot:

- **Stops placed**: of the stops whose location gives something to place (an address, an intersection, a named place or another town), how many are on the map. Design AC2 requires at least 95%. Each stop not placed is listed with the reason.
- **Unknown streets**: names that match no street in the snapshot. They are never displayed.
- **Boundary streets** (on `rebuild`, and on a `collect` that wrote): for each street near a shared ward edge, how many placed entries were within reach of the edge and how many rule 5 counted toward both wards. Check these against the [city ward map](https://www.cityofmelrose.org/745/City-of-Melrose-Ward-and-Precinct-Map). The rule's thresholds are `BOUNDARY_RULE` in `settings.py`.

An entry is not put on the map, and is counted as unmapped, in one of four groups (design R8): **street only**; **no location**; **address not found**, when its location is a named place with no address (`Location: PETRONES`), names an unknown street, or cannot be found; and **outside Melrose**, when it names another town (`[MED] …`) or would land more than 25 m outside the city.

## Layout

The Python package is built as ports and adapters (technical spec T16). The counting, versioning and privacy rules live in a core that imports no PDF, HTTP, database or logging library.

```
src/cities/cli.py                       `cities` command; dispatches to one handler per city
src/cities/melrose/
  domain/                               stdlib types; vocabulary.py holds the known results
  ports/inbound.py, ports/outbound.py   the use cases, and what the core drives
  core/                                 collect | rebuild | reference | sample | export, over loading | publishing, over placing, over rules | locations
  adapters/inbound/cli.py               argument parsing and the printed report
  adapters/outbound/                    wordpress, pdf_reader + log_grammar, log_archive, sqlite_repo, arcgis, reference_files, gazetteer, json_publisher, clock
  stubs.py                              in-memory fakes of every outbound port
  settings.py                           data paths, the start date, the reference layers, the rule 5 thresholds, call_types.txt, categories.toml
  categories.toml                       which call types the map shows, grouped into categories
  composition.py                        the only place adapters are built
  handler.py                            `cities melrose` entry point
data/melrose/raw/                       committed: each PDF as <sha256>.pdf, plus <media id>.json saying which upload it was
data/melrose/reference/                 committed: one GeoJSON file per layer, plus manifest.json
data/melrose/db.sqlite                  git-ignored; `rebuild` recreates it
tests/melrose/                          pytest
site/                                   the map page: src/{main,aggregate,types}.ts, tests/ (vitest)
```

| Outbound port | Adapter |
|---|---|
| `LogSource`: find and fetch published logs | the site's WordPress media API, 2 s between requests |
| `LogReader`: read the entries in a log | pdfplumber lines, through the line grammar |
| `LogArchive`: keep each log as downloaded | files in `data/melrose/raw/` |
| `EntryRepository`: documents, versions, current entries, runs | SQLite |
| `ReferenceSource`: fetch reference layers | ArcGIS REST |
| `ReferenceStore`: keep the reference snapshot | GeoJSON files in `data/melrose/reference/` |
| `Gazetteer`: locate addresses and crossings, describe the wards around a point | the snapshot, with shapely and pyproj in metres (EPSG:26986) |
| `MapPublisher`: publish what the page may show | `entries.json` and `wards.geojson` in `site/public/data/melrose/` |
| `Clock` | the system clock |

## Checks

```sh
uv run pytest
uv run pyright
uv run lint-imports
cd site && npm test && npm run typecheck
```

The import contracts and the pyright settings are in `pyproject.toml`. pyright runs in `standard` mode, because only `standard` reports an adapter whose signature drifted from its port. Each contract was proven on 2026-10-07, and again after phases 2 and 3 extended them, by planting a violation it forbids and seeing exactly that contract report BROKEN. Repeat that after changing a contract.

These tests guard rules that would otherwise fail without any error:

| Invariant | Test |
|---|---|
| The current version is the latest upload covering the entry's date; an entry missing from it is withdrawn | `test_rules.py::test_current_version_is_the_latest_upload_covering_the_entry_date`, `::test_an_entry_missing_from_the_latest_covering_log_is_withdrawn` |
| A withheld entry's location never becomes another entry's location | `test_rules.py::test_trailing_location_never_becomes_the_entry_location`, `test_published_logs.py::test_a_withheld_entrys_location_left_after_an_arrest_is_not_this_entrys` |
| A line that would have fitted on the line before is not joined to it | `test_log_grammar.py::test_a_word_that_would_have_fitted_is_not_a_wrap`, `test_published_logs.py::test_text_after_page_furniture_that_would_have_fitted_is_not_a_location` |
| Every call number printed in a log becomes exactly one stored entry | `test_published_logs.py::test_every_log_since_jul_20_passes_the_completeness_check` |
| Collecting again changes nothing, and `rebuild` equals incremental collection, placements included | `test_use_cases.py::test_collecting_again_writes_nothing`, `::test_rebuild_from_the_archive_equals_incremental_collection` |
| A failed download writes nothing | `test_use_cases.py::test_a_failed_download_writes_nothing` |
| Every adapter inherits its port, and every port method is abstract | `test_ports.py` |
| No word from a location label or household reaches a displayed address | `test_published_placements.py::test_r10_every_word_shown_is_a_house_number_an_at_sign_or_part_of_a_reference_street`, `test_placing.py::test_ac10_the_address_shown_is_rebuilt_without_the_place_name` |
| Another town's address is never placed in Melrose | `test_placing.py::test_what_cannot_be_placed_in_melrose_is_unplaced_with_its_reason`, `test_published_placements.py::test_another_towns_address_is_never_placed_in_melrose` |
| A ward edge counts only for the street that runs along it | `test_placing.py::test_an_edge_no_street_runs_along_adds_no_ward`, `::test_boundary_rows_credit_only_the_street_that_runs_along_the_edge` |
| A missing reference snapshot writes nothing | `test_use_cases.py::test_a_missing_reference_snapshot_writes_nothing` |
| At least 95% of stops with a location to place are on the map (AC2) | `test_published_placements.py::test_ac2_at_least_95_percent_of_stops_with_an_address_or_intersection_are_placed` |
| Only the listed call types of current entries are exported | `test_published_export.py::test_ac5_every_current_entry_of_a_listed_call_type_is_exported_and_nothing_else`, `test_publishing.py::test_only_listed_call_types_of_current_entries_leave` |
| A misspelt call type in `categories.toml` is caught | `test_categories.py::test_every_listed_call_type_is_one_the_logs_use` |
| No word of a published location reaches the export unless it names a street (AC10) | `test_published_export.py::test_ac10_the_pope_entries_show_only_their_address`, `::test_r10_no_word_of_any_published_location_reaches_the_export_unless_it_names_a_street` |
| Arrest results never show sex or age | `test_publishing.py::test_arrests_collapse_and_a_cut_short_result_takes_its_one_full_form`, `test_published_export.py::test_no_arrest_result_carries_sex_or_age` |
| An unmapped record carries no address, point or ward | `test_publishing.py::test_an_unmapped_record_carries_no_address_point_or_ward` |
| A shown entry without a placement, or placed against another snapshot, stops the export | `test_publishing.py::test_a_shown_entry_without_a_placement_refuses_the_export`, `::test_placements_from_another_snapshot_refuse_the_export` |
| The export file keeps the shape the page reads | `test_storage_adapters.py::test_the_export_file_has_exactly_the_appendix_d_shape`, `::test_the_export_file_matches_the_golden_file_the_page_tests_read`, and `site/tests/aggregate.test.ts` on the same golden file |
| Collecting then rebuilding gives the same export, byte for byte apart from `generated_at` (AC11) | `test_cli_end_to_end.py::test_collect_then_collect_again_then_rebuild` |
| Ward stops − extra counts + unmapped stops = total stops, under any filter (AC7) | `site/tests/aggregate.test.ts`, "AC7: the ward table reconciles" |
