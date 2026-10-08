// Filtering and counting for the map page. Python has already decided each record's point, streets
// and wards (technical spec T11); this only adds them up. Free of Leaflet and the DOM, so vitest can
// check the design's acceptance criteria directly.

import type { ExportDocument, ExportRecord, MapExport, UnmappedKind } from "./types";

export const STOPS = "stops";
export const CRASHES = "crashes";
export const WARDS = ["1", "2", "3", "4", "5", "6", "7"];

/** Design R8's unmapped groups, in the order the page lists them. */
export const UNMAPPED: { kind: UnmappedKind; label: string }[] = [
  { kind: "street_only", label: "Street only" },
  { kind: "none", label: "No location" },
  { kind: "unplaced", label: "Address not found" },
  { kind: "outside", label: "Outside Melrose" },
];

export interface Filters {
  from: string; // ISO date, inclusive
  to: string; // ISO date, inclusive
  categories: ReadonlySet<string>;
  stopResults: ReadonlySet<string>; // the stop results ticked under Stops; crashes are never filtered by result
}

export function isMapped(r: ExportRecord): boolean {
  return r.kind === "address" || r.kind === "intersection";
}

function inDates(r: ExportRecord, f: Filters): boolean {
  return r.date >= f.from && r.date <= f.to;
}

function hasResult(r: ExportRecord, f: Filters): boolean {
  return r.category !== STOPS || f.stopResults.has(r.result);
}

/** Records matching every filter: what the markers and the unmapped counts show. */
export function filterRecords(records: readonly ExportRecord[], f: Filters): ExportRecord[] {
  return records.filter((r) => inDates(r, f) && f.categories.has(r.category) && hasResult(r, f));
}

/** The whole collected period: from the first log's first date to the last log's last date. */
export function dateRange(exported: MapExport): { from: string; to: string } {
  const firsts = exported.documents.map((d) => d.first_date).sort();
  const lasts = exported.documents.map((d) => d.last_date).sort();
  return { from: firsts[0] ?? "", to: lasts[lasts.length - 1] ?? "" };
}

/** Stop results to offer under Stops, most frequent first (design R12). */
export function stopResultOptions(records: readonly ExportRecord[]): string[] {
  const counts = countBy(records.filter((r) => r.category === STOPS), (r) => [r.result]);
  return [...counts.keys()].sort((a, b) => (counts.get(b) ?? 0) - (counts.get(a) ?? 0) || a.localeCompare(b));
}

/**
 * Entries per category in the date range, shown beside each Show box (design R4). No tick changes
 * it, so a count reads the same ticked or not (A15).
 */
export function categoryCounts(records: readonly ExportRecord[], f: Filters): Map<string, number> {
  return countBy(records.filter((r) => inDates(r, f)), (r) => [r.category]);
}

/**
 * Stops per result in the date range, shown beside each result box (design R12). The ticks, including
 * the Stops box, do not change it, so a count reads the same ticked or not (A15).
 */
export function stopResultCounts(records: readonly ExportRecord[], f: Filters): Map<string, number> {
  return countBy(records.filter((r) => r.category === STOPS && inDates(r, f)), (r) => [r.result]);
}

export interface Tally {
  total: number;
  mapped: number; // entries with a marker, not distinct markers (design AC4)
  unmapped: Record<UnmappedKind, number>;
}

export function tally(records: readonly ExportRecord[]): Tally {
  const unmapped: Record<UnmappedKind, number> = { street_only: 0, none: 0, unplaced: 0, outside: 0 };
  let mapped = 0;
  for (const r of records) {
    if (isMapped(r)) mapped += 1;
    else unmapped[r.kind as UnmappedKind] += 1;
  }
  return { total: records.length, mapped, unmapped };
}

export interface MarkerGroup {
  category: string;
  lat: number;
  lon: number;
  records: ExportRecord[]; // in date and time order
}

/** One marker per category and distinct point, sized by how many entries it holds (technical spec T7). */
export function markerGroups(records: readonly ExportRecord[]): MarkerGroup[] {
  const groups = new Map<string, MarkerGroup>();
  for (const r of records) {
    if (!isMapped(r) || r.lat === null || r.lon === null) continue;
    const key = `${r.category}|${r.lat}|${r.lon}`;
    const group = groups.get(key) ?? { category: r.category, lat: r.lat, lon: r.lon, records: [] };
    group.records.push(r);
    groups.set(key, group);
  }
  return [...groups.values()];
}

export interface MultiWard {
  entries: number; // entries counted toward more than one ward
  extra: number; // counts beyond one per entry
}

export interface WardRow {
  ward: string;
  stops: number;
  crashes: number;
  stopsPerCrash: number | null; // null when the ward has no crashes or Stops is unticked, shown as "—"
}

export interface WardTable {
  rows: WardRow[];
  stopsMultiWard: MultiWard;
  crashesMultiWard: MultiWard;
  // Design AC7: Σ ward stops − stopsMultiWard.extra + unmappedStops = totalStops.
  unmappedStops: number;
  totalStops: number;
}

/**
 * Stops and crashes per ward (design R6). The date range applies to both columns, an unticked Show box
 * empties its column, and the ticked stop results apply to stops only: a crash's result says nothing
 * about enforcement (A11, A13, A14).
 */
export function wardTable(records: readonly ExportRecord[], f: Filters): WardTable {
  const stops = rankedStops(records, f);
  const crashes = records.filter((r) => r.category === CRASHES && f.categories.has(CRASHES) && inDates(r, f));
  const stopsByWard = countBy(stops, (r) => r.wards);
  const crashesByWard = countBy(crashes, (r) => r.wards);
  const rows = WARDS.map((ward) => {
    const s = stopsByWard.get(ward) ?? 0;
    const c = crashesByWard.get(ward) ?? 0;
    return { ward, stops: s, crashes: c, stopsPerCrash: c === 0 || !f.categories.has(STOPS) ? null : s / c };
  });
  return {
    rows,
    stopsMultiWard: multiWard(stops),
    crashesMultiWard: multiWard(crashes),
    unmappedStops: stops.filter((r) => !isMapped(r)).length,
    totalStops: stops.length,
  };
}

function multiWard(records: readonly ExportRecord[]): MultiWard {
  const many = records.filter((r) => r.wards.length > 1);
  return { entries: many.length, extra: many.reduce((n, r) => n + r.wards.length - 1, 0) };
}

export interface StreetRanking {
  rows: { street: string; stops: number }[];
  counted: number; // stops counted toward at least one street
  countedTwice: number; // intersection stops, counted toward both streets (design R7, AC8a)
}

/**
 * Streets by number of stops (design R7), under the date range, the Stops box and the ticked stop
 * results. Stops with a street but no address count too (AC8), and an intersection stop counts toward
 * both its streets (AC8a).
 */
export function streetRanking(records: readonly ExportRecord[], f: Filters): StreetRanking {
  const stops = rankedStops(records, f);
  const counts = countBy(stops, (r) => r.streets);
  const rows = [...counts.entries()]
    .map(([street, n]) => ({ street, stops: n }))
    .sort((a, b) => b.stops - a.stops || a.street.localeCompare(b.street));
  return {
    rows,
    counted: stops.filter((r) => r.streets.length > 0).length,
    countedTwice: stops.filter((r) => r.streets.length > 1).length,
  };
}

function rankedStops(records: readonly ExportRecord[], f: Filters): ExportRecord[] {
  return records.filter((r) => r.category === STOPS && f.categories.has(STOPS) && inDates(r, f) && hasResult(r, f));
}

/**
 * The message for a date range whose To is earlier than its From (design AC4a), worded after the
 * input just edited, or null when the range is valid. Both ends are inclusive, so From = To is one day.
 */
export function dateError(from: string, to: string, edited: "from" | "to"): string | null {
  if (from <= to) return null;
  return edited === "to" ? "To is earlier than From." : "From is later than To.";
}

function countBy(records: readonly ExportRecord[], keys: (r: ExportRecord) => readonly string[]): Map<string, number> {
  const counts = new Map<string, number>();
  for (const r of records) {
    for (const key of keys(r)) counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return counts;
}

export function formatPerCrash(value: number | null): string {
  return value === null ? "—" : value.toFixed(1);
}

export interface EntryDetails {
  heading: string; // "26-11102 · 2026-09-21 08:58"
  type: string;
  result: string;
  address: string; // "752 FRANKLIN ST @ 8 GARDEN ST", "Vicinity of …", or the unmapped group
  wards: string; // "Ward 4", "Wards 1, 4", or ""
  link: string; // the log's PDF at the entry's page (design R9, AC9)
}

/** What a marker shows for one entry (design R9): only exported fields, never location text. */
export function entryDetails(r: ExportRecord, documents: readonly ExportDocument[]): EntryDetails {
  const doc = documents[r.doc];
  if (!doc) throw new Error(`record ${r.call} names document ${r.doc}, which the export lacks`);
  const time = `${r.time.slice(0, 2)}:${r.time.slice(2)}`;
  const place = r.address ?? UNMAPPED.find((u) => u.kind === r.kind)?.label ?? "";
  return {
    heading: `${r.call} · ${r.date} ${time}`,
    type: r.type,
    result: r.result,
    address: r.vicinity && r.address ? `Vicinity of ${r.address}` : place,
    wards: r.wards.length === 0 ? "" : `${r.wards.length > 1 ? "Wards" : "Ward"} ${r.wards.join(", ")}`,
    link: `${doc.url}#page=${r.page}`,
  };
}
