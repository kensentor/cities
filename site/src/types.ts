// The export contract with the Python side (technical spec Appendix D). The Python adapter test
// pins the same key sets, and both sides read tests/melrose/fixtures/golden/export_sample.json.

export type Kind = "address" | "intersection" | "street_only" | "none" | "unplaced" | "outside";
export type UnmappedKind = Exclude<Kind, "address" | "intersection">;

export interface ExportRecord {
  call: string; // "26-11102"
  date: string; // "2026-09-21"
  time: string; // "0858"
  category: string; // a key of categories[], e.g. "crashes"
  type: string; // call type as published
  result: string; // as published, except arrests are "Arrest" and a cut-short result its one full form
  address: string | null; // rebuilt, label-free; null unless kind is address/intersection
  vicinity: boolean; // published as "Vicinity of:"
  kind: Kind;
  lat: number | null;
  lon: number | null;
  streets: string[]; // ranking keys, display form
  wards: string[]; // "1".."7"; 0–3 entries; empty unless placed
  doc: number; // index into documents[]
  page: number;
}

export interface Category {
  key: string;
  label: string;
}

export interface ExportDocument {
  url: string;
  first_date: string;
  last_date: string;
}

export interface MapExport {
  generated_at: string;
  reference_version: string;
  categories: Category[];
  documents: ExportDocument[];
  records: ExportRecord[];
}

const EXPORT_KEYS = ["categories", "documents", "generated_at", "records", "reference_version"];
const RECORD_KEYS = [
  "address", "call", "category", "date", "doc", "kind", "lat", "lon", "page", "result", "streets", "time", "type",
  "vicinity", "wards",
];

/** The parsed export, or an error naming what differs from the contract, so a drifted export fails loudly. */
export function parseExport(data: unknown): MapExport {
  const keys = (o: object) => Object.keys(o).sort().join(",");
  if (typeof data !== "object" || data === null || keys(data) !== EXPORT_KEYS.join(",")) {
    throw new Error(`entries.json: expected keys ${EXPORT_KEYS.join(", ")}`);
  }
  const exported = data as MapExport;
  const odd = exported.records.find((r) => keys(r) !== RECORD_KEYS.join(","));
  if (odd) {
    throw new Error(`entries.json: record ${odd.call} has keys ${keys(odd)}`);
  }
  return exported;
}
