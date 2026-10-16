import { describe, expect, it } from "vitest";
import golden from "../../tests/melrose/fixtures/golden/export_sample.json";
import {
  CRASHES,
  STOPS,
  type Filters,
  categoryCounts,
  dateError,
  dateRange,
  entryDetails,
  filterRecords,
  formatPerCrash,
  markerGroups,
  pointInPolygon,
  stopResultCounts,
  stopResultOptions,
  streetRanking,
  tally,
  wardTable,
} from "../src/aggregate";
import { type ExportRecord, type MapExport, parseExport } from "../src/types";

// The Python adapter test checks that the JSON publisher still writes this file byte for byte.
const GOLDEN = parseExport(golden);

let n = 0;
function rec(over: Partial<ExportRecord>): ExportRecord {
  n += 1;
  const placed = over.kind === undefined || over.kind === "address" || over.kind === "intersection";
  return {
    call: `26-${1000 + n}`,
    date: "2026-09-21",
    time: "1200",
    category: STOPS,
    type: "MOTOR VEHICLE STOP",
    result: "Verbal Warning",
    address: placed ? "1 MAIN ST" : null,
    vicinity: false,
    kind: "address",
    lat: placed ? 42.46 : null,
    lon: placed ? -71.06 : null,
    streets: ["Main St"],
    wards: placed ? ["4"] : [],
    doc: 0,
    page: 1,
    ...over,
  };
}

const crash = (over: Partial<ExportRecord>) =>
  rec({ category: CRASHES, type: "MOTOR VEHICLE ACCIDENT", result: "* Report taken", ...over });

// Two weeks: stops and crashes on and off the map, on and across ward boundaries.
const RECORDS: ExportRecord[] = [
  rec({ date: "2026-09-14" }),
  rec({ date: "2026-09-21", kind: "intersection", address: "752 FRANKLIN ST @ 8 GARDEN ST", streets: ["Franklin St", "Garden St"], wards: ["1", "4"], lat: 42.47, lon: -71.07 }),
  rec({ date: "2026-09-22", result: "Citation/Warning Issued", wards: ["1", "2", "4"], lat: 42.48 }),
  rec({ date: "2026-09-23", kind: "street_only", streets: ["Franklin St"] }),
  rec({ date: "2026-09-23", kind: "none", streets: [] }),
  rec({ date: "2026-09-24", kind: "unplaced", streets: ["Main St"], result: "Citation/Warning Issued" }),
  rec({ date: "2026-09-25", kind: "outside", streets: [] }),
  rec({ date: "2026-09-27", result: "Arrest", wards: ["6"], lat: 42.45 }),
  crash({ date: "2026-09-21", wards: ["4"] }),
  crash({ date: "2026-09-22", wards: ["1", "4"], lat: 42.47, lon: -71.07 }),
  crash({ date: "2026-09-26", kind: "none", streets: [] }),
];

const BOTH = new Set([STOPS, CRASHES]);
const STOP_RESULTS = new Set(["Verbal Warning", "Citation/Warning Issued", "Arrest"]);
const all: Filters = { from: "2026-09-14", to: "2026-09-27", categories: BOTH, stopResults: STOP_RESULTS };
const only = (...results: string[]): ReadonlySet<string> => new Set(results);
const week: Filters = { ...all, from: "2026-09-21" };

describe("the export contract", () => {
  it("parses the golden export written by the Python publisher", () => {
    expect(GOLDEN.records.map((r) => r.call)).toEqual(["26-11102", "26-11103", "26-11120"]);
    expect(GOLDEN.records[0]?.wards).toEqual(["1", "4"]);
  });

  it("refuses an export whose records carry a key the contract does not name", () => {
    const drifted = JSON.parse(JSON.stringify(GOLDEN)) as MapExport & { records: Record<string, unknown>[] };
    drifted.records[0]!["location"] = "POPE RESIDENCE";
    expect(() => parseExport(drifted)).toThrow(/26-11102/);
  });
});

describe("AC4: date range and Stops", () => {
  it("shows only stops in the range, and markers plus unmapped equal the stops for those dates", () => {
    const shown = filterRecords(RECORDS, { ...week, categories: new Set([STOPS]) });
    expect(shown.every((r) => r.category === STOPS && r.date >= "2026-09-21")).toBe(true);
    const t = tally(shown);
    const source = RECORDS.filter((r) => r.category === STOPS && r.date >= "2026-09-21" && r.date <= "2026-09-27");
    expect(t.mapped + Object.values(t.unmapped).reduce((a, b) => a + b, 0)).toBe(source.length);
    expect(t).toEqual({ total: 7, mapped: 3, unmapped: { street_only: 1, none: 1, unplaced: 1, outside: 1 } });
  });

  it("counts entries, not markers, when several share a point", () => {
    const shared = [rec({}), rec({})];
    expect(markerGroups(shared)).toHaveLength(1);
    expect(markerGroups(shared)[0]?.records).toHaveLength(2);
    expect(tally(shared).mapped).toBe(2);
  });

  it("defaults to the whole collected period", () => {
    expect(dateRange(GOLDEN)).toEqual({ from: "2026-09-21", to: "2026-09-27" });
  });
});

describe("AC5: category options", () => {
  it("come from the export's categories, which pytest pins to Stops and Crashes", () => {
    expect(GOLDEN.categories).toEqual([
      { key: "stops", label: "Stops" },
      { key: "crashes", label: "Crashes" },
    ]);
  });
});

describe("AC6 and AC9: marker details", () => {
  it("names every ward a boundary entry counts toward, and links to its page of the log", () => {
    const [first] = GOLDEN.records;
    expect(entryDetails(first!, GOLDEN.documents)).toEqual({
      heading: "26-11102 · 2026-09-21 08:58",
      type: "MOTOR VEHICLE STOP",
      result: "Citation/Warning Issued",
      address: "752 FRANKLIN ST @ 8 GARDEN ST",
      wards: "Wards 1, 4",
      link: "https://example.test/sep-21.pdf#page=12",
    });
  });

  it("says vicinity, and a single ward", () => {
    const details = entryDetails(rec({ vicinity: true, wards: ["4"] }), GOLDEN.documents);
    expect([details.address, details.wards]).toEqual(["Vicinity of 1 MAIN ST", "Ward 4"]);
  });

  it("groups markers by category, so each layer can be shown alone", () => {
    const groups = markerGroups(filterRecords(RECORDS, week));
    expect(groups.map((g) => [g.category, g.records.length])).toContainEqual([CRASHES, 1]);
    expect(groups.some((g) => g.records.some((r) => r.category !== g.category))).toBe(false);
  });
});

describe("AC7: the ward table reconciles", () => {
  const filters: [string, Filters][] = [
    ["everything", all],
    ["one week", week],
    ["one stop result", { ...all, stopResults: only("Citation/Warning Issued") }],
    ["two stop results", { ...all, stopResults: only("Citation/Warning Issued", "Arrest") }],
    ["no stop results", { ...all, stopResults: only() }],
    ["Stops unticked", { ...all, categories: new Set([CRASHES]) }],
    ["Crashes unticked", { ...all, categories: new Set([STOPS]) }],
    ["nothing in range", { ...all, from: "2026-01-01", to: "2026-01-02" }],
  ];
  it.each(filters)("ward stops − extra counts + unmapped stops = total stops, with %s", (_, f) => {
    const t = wardTable(RECORDS, f);
    const wardStops = t.rows.reduce((sum, row) => sum + row.stops, 0);
    expect(wardStops - t.stopsMultiWard.extra + t.unmappedStops).toBe(t.totalStops);
  });

  it("notes entries counted in more than one ward and the extra counts", () => {
    const t = wardTable(RECORDS, all);
    expect(t.stopsMultiWard).toEqual({ entries: 2, extra: 3 });
    expect(t.crashesMultiWard).toEqual({ entries: 1, extra: 1 });
    expect(t.rows.find((row) => row.ward === "4")).toEqual({ ward: "4", stops: 3, crashes: 2, stopsPerCrash: 1.5 });
  });

  it("shows — for stops per crash in a ward with no crashes", () => {
    const ward6 = wardTable(RECORDS, all).rows.find((row) => row.ward === "6");
    expect(ward6?.crashes).toBe(0);
    expect(formatPerCrash(ward6?.stopsPerCrash ?? null)).toBe("—");
  });

  it("counts no stops with Stops unticked, and no crashes with Crashes unticked (A14)", () => {
    const noStops = wardTable(RECORDS, { ...all, categories: new Set([CRASHES]) });
    expect(noStops.rows.map((row) => row.stops)).toEqual([0, 0, 0, 0, 0, 0, 0]);
    expect(noStops.totalStops).toBe(0);
    expect(noStops.rows.find((row) => row.ward === "4")).toEqual({ ward: "4", stops: 0, crashes: 2, stopsPerCrash: null });
    const noCrashes = wardTable(RECORDS, { ...all, categories: new Set([STOPS]) });
    expect(noCrashes.rows.map((row) => row.crashes)).toEqual([0, 0, 0, 0, 0, 0, 0]);
    expect(noCrashes.rows.find((row) => row.ward === "4")?.stops).toBe(3);
  });
});

describe("AC8 and AC8a: the street ranking", () => {
  it("counts a street-only stop, and an intersection stop toward both streets, noting it", () => {
    const ranking = streetRanking(RECORDS, all);
    expect(ranking.rows).toEqual([
      { street: "Main St", stops: 4 },
      { street: "Franklin St", stops: 2 },
      { street: "Garden St", stops: 1 },
    ]);
    expect(ranking.countedTwice).toBe(1);
  });

  it("leaves the street-only stop off the map but in the unmapped count", () => {
    const streetOnly = RECORDS.filter((r) => r.kind === "street_only");
    expect(markerGroups(streetOnly)).toEqual([]);
    expect(tally(streetOnly).unmapped.street_only).toBe(1);
  });
});

describe("AC4a: an inverted date range", () => {
  it("is reported whichever date was edited, worded after that date", () => {
    expect(dateError("2026-09-22", "2026-09-21", "to")).toBe("To is earlier than From.");
    expect(dateError("2026-09-22", "2026-09-21", "from")).toBe("From is later than To.");
  });

  it("is not an error when From and To are the same day", () => {
    expect(dateError("2026-09-21", "2026-09-21", "to")).toBeNull();
    expect(dateError("2026-09-14", "2026-09-27", "from")).toBeNull();
  });
});

describe("AC12: the stop results ticked under Stops", () => {
  it("change markers, ranking and ward table together", () => {
    const f: Filters = { ...all, categories: new Set([STOPS]), stopResults: only("Citation/Warning Issued") };
    const shown = filterRecords(RECORDS, f);
    expect(shown.every((r) => r.result === "Citation/Warning Issued")).toBe(true);
    expect(markerGroups(shown).flatMap((g) => g.records)).toHaveLength(1);
    expect(streetRanking(RECORDS, f).rows).toEqual([{ street: "Main St", stops: 2 }]);
    const t = wardTable(RECORDS, f);
    expect(t.totalStops).toBe(2);
    expect(t.rows.filter((row) => row.stops > 0).map((row) => row.ward)).toEqual(["1", "2", "4"]);
  });

  it("can be ticked several at once", () => {
    const f: Filters = { ...all, categories: new Set([STOPS]), stopResults: only("Citation/Warning Issued", "Arrest") };
    expect(filterRecords(RECORDS, f).map((r) => r.result).sort()).toEqual([
      "Arrest",
      "Citation/Warning Issued",
      "Citation/Warning Issued",
    ]);
    expect(wardTable(RECORDS, f).totalStops).toBe(3);
  });

  it("never narrow crashes: crash markers and the crashes column stay as they are", () => {
    const f: Filters = { ...all, stopResults: only("Citation/Warning Issued") };
    expect(filterRecords(RECORDS, f).filter((r) => r.category === CRASHES)).toHaveLength(3);
    expect(wardTable(RECORDS, f).rows.find((row) => row.ward === "4")?.crashes).toBe(2);
  });

  it("with none ticked, show no stops but every crash", () => {
    const f: Filters = { ...all, stopResults: only() };
    expect(filterRecords(RECORDS, f).every((r) => r.category === CRASHES)).toBe(true);
    expect(wardTable(RECORDS, f).totalStops).toBe(0);
    expect(streetRanking(RECORDS, f).rows).toEqual([]);
  });

  it("count for nothing when Stops is unticked: no stops anywhere (A14)", () => {
    const noStops: Filters = { ...all, categories: new Set([CRASHES]), stopResults: only("Citation/Warning Issued") };
    expect(filterRecords(RECORDS, noStops).every((r) => r.category === CRASHES)).toBe(true);
    expect(wardTable(RECORDS, noStops).totalStops).toBe(0);
    expect(streetRanking(RECORDS, noStops).rows).toEqual([]);
  });

  it("each show their stops in the date range, ticked or not (A15)", () => {
    const counts = (f: Filters) => Object.fromEntries(stopResultCounts(RECORDS, f));
    expect(counts(all)).toEqual({ "Verbal Warning": 5, "Citation/Warning Issued": 2, Arrest: 1 });
    expect(counts(week)).toEqual({ "Verbal Warning": 4, "Citation/Warning Issued": 2, Arrest: 1 });
    const unticked: Filters = { ...week, categories: new Set([CRASHES]), stopResults: only() };
    expect(counts(unticked)).toEqual(counts(week));
  });

  it("add up to the count beside Stops, which like Crashes' ignores every tick (A15)", () => {
    const perCategory = (f: Filters) => Object.fromEntries(categoryCounts(RECORDS, f));
    expect(perCategory(all)).toEqual({ [STOPS]: 8, [CRASHES]: 3 });
    expect(perCategory({ ...week, categories: new Set(), stopResults: only() })).toEqual({ [STOPS]: 7, [CRASHES]: 3 });
    const results = [...stopResultCounts(RECORDS, all).values()].reduce((a, b) => a + b, 0);
    expect(results).toBe(categoryCounts(RECORDS, all).get(STOPS));
  });

  it("are offered from stops only, most frequent first", () => {
    expect(stopResultOptions(RECORDS)).toEqual(["Verbal Warning", "Citation/Warning Issued", "Arrest"]);
  });
});

describe("a drawn area", () => {
  // A square from 42.45–42.47 N and 71.07–71.05 W, with a notch cut from the north-east corner.
  const square = [
    [42.45, -71.07],
    [42.47, -71.07],
    [42.47, -71.06],
    [42.46, -71.06],
    [42.46, -71.05],
    [42.45, -71.05],
  ] as const;
  const open: Filters = {
    from: "2026-01-01",
    to: "2026-12-31",
    categories: new Set([STOPS, CRASHES]),
    stopResults: new Set(["Verbal Warning"]),
  };

  it("holds points inside, including a concave polygon's inner side, and rejects those outside", () => {
    expect(pointInPolygon(42.455, -71.06, square)).toBe(true);
    expect(pointInPolygon(42.465, -71.065, square)).toBe(true);
    expect(pointInPolygon(42.465, -71.055, square)).toBe(false); // in the notch
    expect(pointInPolygon(42.5, -71.06, square)).toBe(false);
  });

  it("keeps only placed entries inside it, across every count", () => {
    const inside = rec({ lat: 42.455, lon: -71.06 });
    const outside = rec({ lat: 42.5, lon: -71.06 });
    const unplaced = rec({ kind: "unplaced" });
    const insideCrash = crash({ lat: 42.455, lon: -71.065 });
    const records = [inside, outside, unplaced, insideCrash];
    const f = { ...open, area: square.map((p) => [...p] as [number, number]) };

    expect(filterRecords(records, f)).toEqual([inside, insideCrash]);
    expect(categoryCounts(records, f).get(STOPS)).toBe(1);
    expect(stopResultCounts(records, f).get("Verbal Warning")).toBe(1);
    expect(wardTable(records, f).totalStops).toBe(1);
    expect(streetRanking(records, f).rows).toEqual([{ street: "Main St", stops: 1 }]);
  });

  it("changes nothing when there is no area", () => {
    const records = [rec({}), rec({ kind: "unplaced" })];
    expect(filterRecords(records, { ...open, area: null })).toEqual(records);
    expect(filterRecords(records, open)).toEqual(records);
  });
});
