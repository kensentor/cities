# Melrose traffic stops map — design spec

- **Status:** Approved by Ken Hoffmann, 2026-10-03. Amended with A1–A6 from the technical spec, approved by Ken Hoffmann, 2026-10-03, with A7–A9, approved by Ken Hoffmann, 2026-10-07, with A10–A11, approved by Ken Hoffmann, 2026-10-08, and with A12–A17, asked for and approved by Ken Hoffmann, 2026-10-08, and with A18, asked for by Ken Hoffmann, 2026-10-16.
- **Date:** 2026-10-03
- **Author:** Ken Hoffmann
- **Ticket:** none
- **Technical spec:** [technical.md](technical.md) (Approved 2026-10-07)

## Problem and motive

The Melrose Police Department publishes its dispatch log every week at [melrosepolice.net/police-logs](https://melrosepolice.net/police-logs/), one document per week. The log is public, but in that form nobody can see a pattern: where traffic stops happen, whether they track where crashes happen, or how they are spread across the city's wards. The suspicion this project tests is that most traffic stops fall on a few specific streets.

It is a personal project for now, but its findings may be shown to Melrose officials as evidence, and a public version is planned. Any result it shows therefore has to be traceable back to the department's own records.

## Goals

The project exists to answer these questions:

- **G1** — Where are Melrose police focusing their traffic efforts?
- **G2** — How does that align with busy streets, with crash rates? *(v1 answers the crash half from the blotter. Busy streets need outside data and are under Later.)*
- **G3** — Are they policing Melrose's wards equally, measured as the number of stops per ward?
- **G4** — Every figure it shows can be checked against the department's published logs, so that it stands up as evidence.

## Audience

The first user and maintainer is the author, running it on their own machine. A later public version would be read by Melrose residents and officials, so nothing displayed in v1 should be unfit for public view.

## Scope

### In the first version

- Every dispatch-log entry from Jan 1, 2024 onward (the first log covers the week of Jan 1, 2024) is collected and stored, whatever its call type (A16, A18).
- A map of Melrose with the 7 ward boundaries. It shows markers for stops and crashes, filtered by date range, category, and the result of a stop. Crashes are MOTOR VEHICLE ACCIDENT, ACCIDENT HIT & RUN and MVA - Not Investigated (D2).
- A ranking of streets by number of stops, and a per-ward table of stops, crashes and stops per crash. Both follow the current filters.
- New weekly logs are collected by running a command by hand (D9).

### Non-goals

- Showing call types other than MOTOR VEHICLE STOP and the three crash types. They are stored, but not displayed.
- Free-text or address search. Filtering covers only date range, category and result.
- Information about drivers or demographics. The logs publish none, except that arrest results give sex and age band (e.g. "Arrest 17 and Over Male"), and those are displayed only as "Arrest" (D10).
- Recovering entries the department withholds under the Domestic Violence Act of 2014.
- Judging whether any single stop was justified.

### Later

- Loading the archive back to 2014.
- Picking up new weekly logs without manual action (formerly R13 and AC13).
- Adding outside data as map layers: MassDOT crash and pedestrian-injury data, and traffic volumes for "busy streets" (G2).
- Public hosting.
- Comparing wards per resident or per mile of road, as well as by raw count.
- A time-of-day filter.
- Optional layers for Directed Patrol, TRAFFIC, parking complaints and tows.
- Places other than Melrose, MA. The only preparation in v1 is a separate namespace for each city, with no code shared between cities (D12).

## Current state

Nothing has been built yet. What was checked on 2026-10-03:

- **Blotter:** one PDF per week, published on the police-logs page. Each entry has a call number (e.g. `26-11102`), a time, a call type, a result (e.g. "Verbal Warning", "Citation/Warning Issued") and usually a location. Entries are grouped under a date heading. The department has already removed names (the `ID:` lines are blank) and withholds some entries entirely, which shows up as gaps in the call numbers.
- **Location formats seen:** an exact address; an intersection (`752 FRANKLIN ST @ 8 GARDEN ST`); a street with no number (`FRANKLIN ST`); a named place (`[MEL 1243] POPE RESIDENCE - 744 LYNN FELLS PKWY`); `Vicinity of: …`; or no location at all. In the week of Sep 21–27, 2026, 142 of 187 entries had a location and 38 were MOTOR VEHICLE STOP. (An earlier count of 183 missed 4 entries that a text extractor had merged into the lines above them.)
- **Archive depth:** the site holds 774 logs back to 2014-03-15 (verified through its media API). The department sometimes re-issues a log with different contents, and old logs are re-uploaded among new ones.
- **Ward boundaries:** published by MassGIS ([Wards and Precincts 2022](https://gis.data.mass.gov/datasets/massgis::wards-and-precincts-2022-feature-service/explore)) and as a [city PDF](https://www.cityofmelrose.org/745/City-of-Melrose-Ward-and-Precinct-Map).

## Requirements

| ID | Priority | Goal | Requirement |
|---|---|---|---|
| <a name="r1"></a>R1 | Must | G1–G4 | Collect every entry in every weekly dispatch log covering Jan 1, 2024 onward, of every call type (A16, A18). An entry printed with a call type and no result is stored with an empty result; the entries of a day whose date heading the log lost take that day's date from its overnight reset in call times (A17). An entry printed without its call number is stored under the call its own Refer To line names; one with no such line is reported instead, since it has no key (A7). |
| <a name="r2"></a>R2 | Must | G4 | Store each entry with its call number, date, time, call type, result, and location text exactly as published, plus which weekly log it came from. |
| <a name="r3"></a>R3 | Must | G1, G3 | Place each entry whose location is an address or intersection at a point in Melrose. An entry whose location can't be placed, or that would land outside Melrose, is counted as unmapped rather than shown in the wrong place. An entry's location is its first location line, and only if it comes before the entry's ID, Refer To or Charges lines; any other location line is usually left by an entry the department withheld, and is kept in storage but never used (A8). |
| <a name="r4"></a>R4 | Must | G1, G2 | Show a map of Melrose with markers for stops (MOTOR VEHICLE STOP) and crashes (MOTOR VEHICLE ACCIDENT, ACCIDENT HIT & RUN, MVA - Not Investigated), filtered by a date range and by category. If To is earlier than From, the page says so and keeps showing the last valid range (A12). Beside each category is its number of entries in the date range, the same whether it is ticked or not (A15). |
| <a name="r5"></a>R5 | Must | G3 | Show the 7 ward boundaries on the map and assign each mapped entry to a ward. An entry on a stretch of street that forms a ward boundary counts toward every ward that boundary separates: two, or three where boundaries meet. |
| <a name="r6"></a>R6 | Must | G2, G3 | Show a per-ward table of stops, crashes and stops per crash for the current filters, with a note giving how many of them were counted in more than one ward and how many extra counts that adds. The date range and the Show boxes apply to both columns: an unticked category counts as 0, and stops per crash then shows "—" (A14). The stop results ticked beneath Stops (R12) apply to stops only, since a crash's result says nothing about enforcement (A11, A13). |
| <a name="r7"></a>R7 | Must | G1 | Show streets ranked by number of stops for the current filters. The ranking includes stops that have a street but no address. An intersection stop counts toward both streets, and the ranking notes how many stops were counted twice this way. With Stops unticked, the ranking is empty (A14). |
| <a name="r8"></a>R8 | Must | G3, G4 | Next to the map, show how many entries in the current filter are not on the map, split into street only, no location, address not found, and outside Melrose (an entry whose location names another town, A9). |
| <a name="r9"></a>R9 | Must | G4 | Selecting a marker shows its call number, date, time, call type, result (any arrest result shown as "Arrest") and address, with a link to the weekly log it came from. |
| <a name="r10"></a>R10 | Must | G4 | Display only the address part of a location, never the name of a place or household. The original text stays in storage. |
| <a name="r11"></a>R11 | Must | G3, G4 | Collecting a week that was already collected changes nothing: no duplicates and no changed counts. |
| <a name="r12"></a>R12 | Should | G1 | Filter stops by result: one checkbox per stop result (e.g. Verbal Warning, Citation/Warning Issued, Unit Clear) beneath Stops, any number ticked. Crashes are not filtered by result (A13). Beside each result is its number of stops in the date range, the same whether it is ticked or not (A15). A result the log prints cut short is shown as its full form when only one known result completes it (`Citation/Warning` as Citation/Warning Issued), so the filter catches it; storage keeps the printed text (A10). |

## Acceptance criteria

- <a name="ac1"></a>**AC1** (R1, R2) — WHEN the Sep 21–27, 2026 log is collected THEN the number of stored entries for that week equals the number of call entries in that document, and the fields of 10 randomly chosen entries match the document word for word.
- <a name="ac2"></a>**AC2** (R3) — WHEN all collected stops whose location is an address or intersection are counted THEN at least 95% of them appear as markers.
- <a name="ac3"></a>**AC3** (R3) — WHEN 20 random markers are compared with the locations given in their log entries THEN every one is within one block of that location.
- <a name="ac4"></a>**AC4** (R4) — WHEN a date range and Stops are selected THEN only stops dated within that range appear, and the marker count plus the unmapped count equals the number of stops in the source logs for those dates.
- <a name="ac4a"></a>**AC4a** (R4) — WHEN To is set earlier than From, or From later than To, THEN the page says so beside the dates, and the map and tables keep showing the last valid range, which the message names.
- <a name="ac5"></a>**AC5** (R4) — WHEN the call-type filter is opened THEN it offers only Stops and Crashes.
- <a name="ac6"></a>**AC6** (R5) — WHEN the map is shown THEN all 7 ward boundaries are drawn and labelled, and a selected marker shows its ward, or every ward it counts toward if it sits on a boundary street.
- <a name="ac7"></a>**AC7** (R6, R8) — WHEN the filters change THEN the ward table updates, and the ward stop counts, minus the extra counts noted for stops counted in more than one ward, plus the unmapped stop count, add up to the total stops matching the filters. A ward with no crashes shows "—" for stops per crash.
- <a name="ac8"></a>**AC8** (R7) — WHEN a stop's location is `FRANKLIN ST` with no number THEN it counts toward Franklin St in the street ranking and appears in the unmapped count, not on the map.
- <a name="ac8a"></a>**AC8a** (R7) — WHEN a stop's location is `752 FRANKLIN ST @ 8 GARDEN ST` THEN it counts once toward Franklin St and once toward Garden St, and is included in the ranking's count of stops counted twice.
- <a name="ac9"></a>**AC9** (R9) — WHEN a marker is selected THEN its details are shown, and the link opens the weekly log that contains its call number.
- <a name="ac10"></a>**AC10** (R10) — WHEN an entry's location is `[MEL 1243] POPE RESIDENCE - 744 LYNN FELLS PKWY` THEN the screen shows `744 LYNN FELLS PKWY`, and "POPE" appears nowhere on it.
- <a name="ac11"></a>**AC11** (R11) — WHEN a week is collected a second time THEN every count shown is unchanged.
- <a name="ac12"></a>**AC12** (R12) — WHEN only Citation/Warning Issued is ticked beneath Stops THEN the only stops shown are those, and the street ranking and ward table update to match; crashes are unaffected.

## Data

- **Dispatch logs** from the Melrose Police Department: public, weekly, and stored indefinitely. They are incomplete by design: entries withheld under the Domestic Violence Act of 2014 never appear, and no attempt is made to recover them.
- **People:** the department already removes names. Location labels can still name a household (e.g. "POPE RESIDENCE"). The label is kept in storage for checking against the source, but is never displayed (R10). Arrest results carry sex and age band, and are displayed only as "Arrest" (D10).
- **Ward boundaries:** MassGIS Wards and Precincts (2022). These change only when the city redistricts.
- **Freshness:** as current as the last manual collection. The department posted logs 1–11 days after each week ended (Jul–Sep 2026), so data can lag the events by up to about two weeks.

## Constraints

- **Low cost.** The author pays for it personally. It runs on the author's machine first, and later on a host they pay for.
- **Melrose, MA only in v1.** That is the question being asked. Other places are under Later (D12).
- **No technologies decided.** These are left to the technical spec.

## Success measures

- For any date range in the collected period, the author can answer G1–G3 from the street ranking and the ward table without opening the source documents.
- AC1–AC11 pass.
- Any figure shown to an official can be traced to specific call numbers in the department's logs.

## Assumptions

- The log format has stayed the same since Jan 2024, apart from the variations the parser handles (A16), and the call-type labels are used consistently. A 2018 log carries `Narrative:` lines not seen since, so earlier years need checking before a backfill.
- The three crash call types are a reasonable stand-in for crashes until MassDOT data is added. The blotter has no pedestrian or bicycle call type, so it can't separate those crashes.
- The 2022 ward boundaries are still current.

## Decisions

- **D1** — Display only stops and crashes (D2). Rejected: TRAFFIC, because the two sample entries look like calls about road conditions, not enforcement; Directed Patrol, which the author judged too vague, although the sample shows it repeating at the same intersections around 0650–0710 and may be worth another look; parking complaints and tows. All of them are stored anyway, so they can be added later at no extra cost.
- **D2** — Use the blotter's crash entries as crashes in v1: MOTOR VEHICLE ACCIDENT, ACCIDENT HIT & RUN and MVA - Not Investigated, grouped as one category, with each marker still showing its exact call type. *(Amended, A5: the original counted MOTOR VEHICLE ACCIDENT only, which leaves out about 13% of crashes.)* Rejected: waiting for MassDOT data, which would hold v1 up (MassDOT comes under Later); leaving out MVA - Not Investigated, because an uninvestigated crash is still a crash.
- **D3** — Measure "policed equally" by raw stops per ward, alongside stops per crash. Rejected for v1: per resident and per mile of road, because both need outside data.
- **D4** — Count stops without a usable location and show that count, rather than placing them approximately. Rejected: putting street-only stops at the middle of the street, which suggests a precision the log doesn't have; and dropping them quietly, which would undercount wards without anyone noticing.
- **D5** — Start from the week of Jul 20, 2026. *(Amended, A16: from Jan 1, 2025; A18: from Jan 1, 2024.)* Rejected: loading the full archive to 2014 in v1, because the format may have changed over 12 years and would hold up the first version.
- **D6** — Display addresses only, never place names. Rejected: showing locations as published, which would put household names on a public map.
- **D7** — A stop on a ward-boundary street counts toward every ward the boundary separates (two, or three where boundaries meet), and the UI says how many stops were counted more than once and how many extra counts that adds. *(Amended, A3: three-ward cases were found at 9 of 388 placed entries.)* Rejected: assigning it to whichever ward the point falls in, since that depends on map precision rather than anything in the log, and the main enforcement streets may well be the boundaries.
- **D8** — An intersection stop counts toward both streets in the ranking, and the UI says how many were counted twice. Rejected: the first street listed, because nothing shows it is the street where the stop happened; and the busier street, which needs traffic-volume data that v1 doesn't have.
- **D9** — Collect new logs by running a command by hand. *(Amended, A1: R13 and AC13, automatic pickup, moved to Later.)* Rejected for v1: a scheduled job on the author's Mac or in the cloud.
- **D10** — Display any arrest result as "Arrest", and store the original wording. *(Amended, A2.)* Rejected: showing it as published, because sex and age band with an exact place and time could help identify a person on a public map.
- **D11** — Count address or intersection entries that couldn't be placed as a third unmapped group, "address not found". *(Amended, A4.)* Rejected: folding them into "no location", which would hide a placement failure as a gap in the log.
- **D12** — Other places move from a non-goal to Later. v1 prepares for them only by giving each city its own namespace (command, code package and data directory), with no code shared between cities until a second city exists (technical spec T13). *(Amended, A6.)* Rejected: keeping other places a non-goal, which would leave the per-city namespace unexplained; building shared multi-city support now, whose shape would be a guess with only one city.

## Open questions

| # | Question | Owner | Blocks |
|---|---|---|---|
| Q1 | Does the archive before 2018 use the same format? Logs from 2025–26 do, with the variations A16 handles; a 2018 log adds `Narrative:` lines; the 2014 logs are daily. | Technical spec | Later (backfill) |
| Q2 | What do the TRAFFIC and Directed Patrol call types mean? | Melrose PD (ask) | Nothing in v1 |
