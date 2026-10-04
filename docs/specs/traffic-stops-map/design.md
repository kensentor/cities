# Melrose traffic stops map — design spec

- **Status:** Approved by Ken Hoffmann, 2026-10-03
- **Date:** 2026-10-03
- **Author:** Ken Hoffmann
- **Ticket:** none
- **Technical spec:** not yet written

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

- Every dispatch-log entry from the week of Jul 20, 2026 onward is collected and stored, whatever its call type.
- A map of Melrose with the 7 ward boundaries. It shows markers for motor vehicle stops and motor vehicle accidents, filtered by date range, call type and result.
- A ranking of streets by number of stops, and a per-ward table of stops, crashes and stops per crash. Both follow the current filters.
- New weekly logs are picked up as they are posted.

### Non-goals

- Places other than Melrose, MA.
- Showing call types other than MOTOR VEHICLE STOP and MOTOR VEHICLE ACCIDENT. They are stored, but not displayed.
- Free-text or address search. Filtering covers only date range, call type and result.
- Information about drivers or demographics. The logs don't publish it.
- Recovering entries the department withholds under the Domestic Violence Act of 2014.
- Judging whether any single stop was justified.

### Later

- Loading the archive back to 2014.
- Adding outside data as map layers: MassDOT crash and pedestrian-injury data, and traffic volumes for "busy streets" (G2).
- Public hosting.
- Comparing wards per resident or per mile of road, as well as by raw count.
- A time-of-day filter.
- Optional layers for Directed Patrol, TRAFFIC, parking complaints and tows.

## Current state

Nothing has been built yet. What was checked on 2026-10-03:

- **Blotter:** one PDF per week, published on the police-logs page. Each entry has a call number (e.g. `26-11102`), a time, a call type, a result (e.g. "Verbal Warning", "Citation/Warning Issued") and usually a location. Entries are grouped under a date heading. The department has already removed names (the `ID:` lines are blank) and withholds some entries entirely, which shows up as gaps in the call numbers.
- **Location formats seen:** an exact address; an intersection (`752 FRANKLIN ST @ 8 GARDEN ST`); a street with no number (`FRANKLIN ST`); a named place (`[MEL 1243] POPE RESIDENCE - 744 LYNN FELLS PKWY`); `Vicinity of: …`; or no location at all. In the week of Sep 21–27, 2026, about 125 of 183 entries had a location and 38 were MOTOR VEHICLE STOP.
- **Archive depth:** the listing page shows logs back to Jul 20, 2026. The author reports that the archive goes back to 2014. This was not verified.
- **Ward boundaries:** published by MassGIS ([Wards and Precincts 2022](https://gis.data.mass.gov/datasets/massgis::wards-and-precincts-2022-feature-service/explore)) and as a [city PDF](https://www.cityofmelrose.org/745/City-of-Melrose-Ward-and-Precinct-Map).

## Requirements

| ID | Priority | Goal | Requirement |
|---|---|---|---|
| R1 | Must | G1–G4 | Collect every entry in every weekly dispatch log from the week of Jul 20, 2026 onward, of every call type. |
| R2 | Must | G4 | Store each entry with its call number, date, time, call type, result, and location text exactly as published, plus which weekly log it came from. |
| R3 | Must | G1, G3 | Place each entry whose location is an address or intersection at a point in Melrose. An entry whose location can't be placed, or that would land outside Melrose, is counted as unmapped rather than shown in the wrong place. |
| R4 | Must | G1, G2 | Show a map of Melrose with markers for MOTOR VEHICLE STOP and MOTOR VEHICLE ACCIDENT entries, filtered by a date range and by call type. |
| R5 | Must | G3 | Show the 7 ward boundaries on the map and assign each mapped entry to a ward. An entry on a stretch of street that forms the boundary between two wards counts toward both. |
| R6 | Must | G2, G3 | Show a per-ward table of stops, crashes and stops per crash for the current filters, with a note giving how many of them were counted in two wards. |
| R7 | Must | G1 | Show streets ranked by number of stops for the current filters. The ranking includes stops that have a street but no address. An intersection stop counts toward both streets, and the ranking notes how many stops were counted twice this way. |
| R8 | Must | G3, G4 | Next to the map, show how many entries in the current filter are not on the map, split into street only and no location. |
| R9 | Must | G4 | Selecting a marker shows its call number, date, time, call type, result and address, with a link to the weekly log it came from. |
| R10 | Must | G4 | Display only the address part of a location, never the name of a place or household. The original text stays in storage. |
| R11 | Must | G3, G4 | Collecting a week that was already collected changes nothing: no duplicates and no changed counts. |
| R12 | Should | G1 | Filter by result (e.g. Verbal Warning, Citation/Warning Issued). |
| R13 | Should | G1 | Pick up newly posted weekly logs without manual action. |

## Acceptance criteria

- **AC1** (R1, R2) — WHEN the Sep 21–27, 2026 log is collected THEN the number of stored entries for that week equals the number of call entries in that document, and the fields of 10 randomly chosen entries match the document word for word.
- **AC2** (R3) — WHEN all collected stops whose location is an address or intersection are counted THEN at least 95% of them appear as markers.
- **AC3** (R3) — WHEN 20 random markers are compared with the locations given in their log entries THEN every one is within one block of that location.
- **AC4** (R4) — WHEN a date range and MOTOR VEHICLE STOP are selected THEN only stops dated within that range appear, and the marker count plus the unmapped count equals the number of stops in the source logs for those dates.
- **AC5** (R4) — WHEN the call-type filter is opened THEN it offers only MOTOR VEHICLE STOP and MOTOR VEHICLE ACCIDENT.
- **AC6** (R5) — WHEN the map is shown THEN all 7 ward boundaries are drawn and labelled, and a selected marker shows its ward, or both wards if it sits on a boundary street.
- **AC7** (R6, R8) — WHEN the filters change THEN the ward table updates, and the ward stop counts, minus the stops noted as counted in two wards, plus the unmapped stop count, add up to the total stops matching the filters. A ward with no crashes shows "—" for stops per crash.
- **AC8** (R7) — WHEN a stop's location is `FRANKLIN ST` with no number THEN it counts toward Franklin St in the street ranking and appears in the unmapped count, not on the map.
- **AC8a** (R7) — WHEN a stop's location is `752 FRANKLIN ST @ 8 GARDEN ST` THEN it counts once toward Franklin St and once toward Garden St, and is included in the ranking's count of stops counted twice.
- **AC9** (R9) — WHEN a marker is selected THEN its details are shown, and the link opens the weekly log that contains its call number.
- **AC10** (R10) — WHEN an entry's location is `[MEL 1243] POPE RESIDENCE - 744 LYNN FELLS PKWY` THEN the screen shows `744 LYNN FELLS PKWY`, and "POPE" appears nowhere on it.
- **AC11** (R11) — WHEN a week is collected a second time THEN every count shown is unchanged.
- **AC12** (R12) — WHEN the result filter is set to Citation/Warning Issued THEN only those stops are shown, and the street ranking and ward table update to match.
- **AC13** (R13) — WHEN a new weekly log is posted THEN its entries appear within 3 days without anyone acting.

## Data

- **Dispatch logs** from the Melrose Police Department: public, weekly, and stored indefinitely. They are incomplete by design: entries withheld under the Domestic Violence Act of 2014 never appear, and no attempt is made to recover them.
- **People:** the department already removes names. Location labels can still name a household (e.g. "POPE RESIDENCE"). The label is kept in storage for checking against the source, but is never displayed (R10).
- **Ward boundaries:** MassGIS Wards and Precincts (2022). These change only when the city redistricts.
- **Freshness:** a week behind the department at most, since the department itself publishes weekly.

## Constraints

- **Low cost.** The author pays for it personally. It runs on the author's machine first, and later on a host they pay for.
- **Melrose, MA only.** That is the question being asked.
- **No technologies decided.** These are left to the technical spec.

## Success measures

- For any date range in the collected period, the author can answer G1–G3 from the street ranking and the ward table without opening the source documents.
- AC1–AC11 pass.
- Any figure shown to an official can be traced to specific call numbers in the department's logs.

## Assumptions

- The weekly log format has stayed the same since Jul 20, 2026, and the call-type labels MOTOR VEHICLE STOP and MOTOR VEHICLE ACCIDENT are used consistently.
- A MOTOR VEHICLE ACCIDENT entry is a reasonable stand-in for a crash until MassDOT data is added.
- The 2022 ward boundaries are still current.
- The archive goes back to 2014 (as the author reports; not verified).

## Decisions

- **D1** — Display only MOTOR VEHICLE STOP and MOTOR VEHICLE ACCIDENT. Rejected: TRAFFIC, because the two sample entries look like calls about road conditions, not enforcement; Directed Patrol, which the author judged too vague, although the sample shows it repeating at the same intersections around 0650–0710 and may be worth another look; parking complaints and tows. All of them are stored anyway, so they can be added later at no extra cost.
- **D2** — Use the blotter's MOTOR VEHICLE ACCIDENT entries as crashes in v1. Rejected: waiting for MassDOT data, which would hold v1 up. MassDOT comes under Later.
- **D3** — Measure "policed equally" by raw stops per ward, alongside stops per crash. Rejected for v1: per resident and per mile of road, because both need outside data.
- **D4** — Count stops without a usable location and show that count, rather than placing them approximately. Rejected: putting street-only stops at the middle of the street, which suggests a precision the log doesn't have; and dropping them quietly, which would undercount wards without anyone noticing.
- **D5** — Start from the week of Jul 20, 2026. Rejected: loading the full archive to 2014 in v1, because the format may have changed over 12 years and would hold up the first version.
- **D6** — Display addresses only, never place names. Rejected: showing locations as published, which would put household names on a public map.
- **D7** — A stop on a ward-boundary street counts toward both wards, and the UI says how many were counted twice. Rejected: assigning it to whichever ward the point falls in, since that depends on map precision rather than anything in the log, and the main enforcement streets may well be the boundaries.
- **D8** — An intersection stop counts toward both streets in the ranking, and the UI says how many were counted twice. Rejected: the first street listed, because nothing shows it is the street where the stop happened; and the busier street, which needs traffic-volume data that v1 doesn't have.

## Open questions

| # | Question | Owner | Blocks |
|---|---|---|---|
| Q1 | Does the archive before Jul 2026 use the same format? | Technical spec | Later (backfill) |
| Q2 | What do the TRAFFIC and Directed Patrol call types mean? | Melrose PD (ask) | Nothing in v1 |
