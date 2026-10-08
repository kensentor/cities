// The map page: loads the export once, keeps every filter in memory, and redraws from aggregate.ts.
// All text is set with textContent, so nothing in the export is ever parsed as HTML.

import L from "leaflet";
import "leaflet/dist/leaflet.css";
import "./style.css";
import {
  type Filters,
  type MarkerGroup,
  STOPS,
  UNMAPPED,
  dateError,
  dateRange,
  entryDetails,
  filterRecords,
  formatPerCrash,
  markerGroups,
  stopResultOptions,
  streetRanking,
  tally,
  wardTable,
} from "./aggregate";
import { type MapExport, parseExport } from "./types";

// Categorical slots in fixed order, one per category in the export's order; a category keeps its
// colour whatever is filtered.
const SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"];
const DATA = `${import.meta.env.BASE_URL}data/melrose/`;

function el<K extends keyof HTMLElementTagNameMap>(tag: K, text?: string, className?: string): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function byId<T extends HTMLElement>(id: string): T {
  const node = document.getElementById(id);
  if (!node) throw new Error(`#${id} missing from index.html`);
  return node as T;
}

async function fetchJson(name: string): Promise<unknown> {
  const response = await fetch(DATA + name);
  if (!response.ok) throw new Error(`${name}: HTTP ${response.status}`);
  return response.json();
}

async function main(): Promise<void> {
  let exported: MapExport;
  let wards: GeoJSON.FeatureCollection;
  try {
    exported = parseExport(await fetchJson("entries.json"));
    wards = (await fetchJson("wards.geojson")) as GeoJSON.FeatureCollection;
  } catch (error) {
    byId("status").textContent =
      `Could not load the export (${String(error)}). Run \`uv run cities melrose export\` from the repo root.`;
    return;
  }
  const colour = new Map(exported.categories.map((c, i) => [c.key, SERIES[i % SERIES.length] ?? "#666"]));
  const label = new Map(exported.categories.map((c) => [c.key, c.label]));

  const range = dateRange(exported);
  const latest = range.to;
  byId("status").textContent =
    `Logs through ${latest} · exported ${exported.generated_at.slice(0, 16).replace("T", " ")} UTC · reference ${exported.reference_version}`;

  const map = L.map("map", { preferCanvas: true });
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  }).addTo(map);
  const outlines = L.geoJSON(wards, {
    style: { color: "#3d3d3a", weight: 2, opacity: 0.8, fillColor: "#3d3d3a", fillOpacity: 0.03 },
    interactive: false,
  }).addTo(map);
  for (const feature of wards.features) {
    const props = feature.properties as { ward: string; label: [number, number] };
    L.tooltip({ permanent: true, direction: "center", className: "ward-label", interactive: false })
      .setLatLng([props.label[1], props.label[0]])
      .setContent(`Ward ${props.ward}`)
      .addTo(map);
  }
  map.fitBounds(outlines.getBounds());
  const markers = L.layerGroup().addTo(map);

  const from = byId<HTMLInputElement>("from");
  const to = byId<HTMLInputElement>("to");
  for (const input of [from, to]) {
    input.min = range.from;
    input.max = range.to;
  }
  from.value = range.from;
  to.value = range.to;

  // While To is earlier than From, the map and tables keep the last valid range, and the message
  // says which range that is (design AC4a).
  let shownRange = { from: range.from, to: range.to };
  let rangeError: string | null = null;
  const dateMessage = byId("date-error");
  function onDateChange(edited: "from" | "to"): void {
    const next = { from: from.value || range.from, to: to.value || range.to };
    rangeError = dateError(next.from, next.to, edited);
    if (rangeError === null) shownRange = next;
    for (const input of [from, to]) {
      if (rangeError === null) input.removeAttribute("aria-invalid");
      else input.setAttribute("aria-invalid", "true");
    }
    dateMessage.hidden = rangeError === null;
    dateMessage.textContent =
      rangeError === null ? "" : `${rangeError} The map and tables still show ${shownRange.from} to ${shownRange.to}.`;
    render();
  }
  from.addEventListener("change", () => onDateChange("from"));
  to.addEventListener("change", () => onDateChange("to"));

  function checkbox(text: string, set: Set<string>, key: string, className: string): HTMLLabelElement {
    const box = el("input");
    box.type = "checkbox";
    box.checked = true;
    box.addEventListener("change", () => {
      if (box.checked) set.add(key);
      else set.delete(key);
      render();
    });
    const row = el("label", undefined, className);
    row.append(box, el("span", text));
    return row;
  }

  // Unticking Stops removes stops from the map and tables whatever results are ticked, so its result
  // boxes are disabled meanwhile but keep their state for when Stops is ticked again (A14).
  const categoryBoxes = byId("categories");
  const checked = new Set(exported.categories.map((c) => c.key));
  const stopResults = new Set(stopResultOptions(exported.records));
  for (const c of exported.categories) {
    const row = checkbox(c.label, checked, c.key, "check");
    const swatch = el("span", undefined, "swatch");
    swatch.style.background = colour.get(c.key) ?? "";
    row.insertBefore(swatch, row.lastChild);
    categoryBoxes.append(row);
    if (c.key === STOPS) {
      const results = el("fieldset", undefined, "subchecks");
      row.querySelector("input")?.addEventListener("change", () => {
        results.disabled = !checked.has(STOPS);
      });
      results.setAttribute("role", "group");
      results.setAttribute("aria-label", "Stop results");
      for (const option of stopResults) results.append(checkbox(option, stopResults, option, "check"));
      categoryBoxes.append(results);
    }
  }

  function filters(): Filters {
    return { from: shownRange.from, to: shownRange.to, categories: checked, stopResults };
  }

  function popup(group: MarkerGroup): HTMLElement {
    const box = el("div", undefined, "popup");
    box.append(el("strong", `${group.records.length} ${label.get(group.category) ?? group.category}`.toLowerCase()));
    for (const r of group.records) {
      const d = entryDetails(r, exported.documents);
      const item = el("div", undefined, "entry");
      const link = el("a", d.heading);
      link.href = d.link;
      link.target = "_blank";
      link.rel = "noopener";
      item.append(link, el("div", `${d.type} — ${d.result}`), el("div", d.address));
      if (d.wards) item.append(el("div", d.wards, "muted"));
      box.append(item);
    }
    return box;
  }

  function render(): void {
    if (rangeError !== null) return;
    const f = filters();
    const shown = filterRecords(exported.records, f);

    markers.clearLayers();
    for (const group of markerGroups(shown)) {
      const n = group.records.length;
      const first = group.records[0];
      L.circleMarker([group.lat, group.lon], {
        radius: 4 + 2.5 * Math.sqrt(n),
        color: "#ffffff",
        weight: 1.5,
        fillColor: colour.get(group.category) ?? "#666",
        fillOpacity: 0.85,
      })
        .bindTooltip(`${n} × ${label.get(group.category) ?? ""} · ${first?.address ?? ""}`)
        .bindPopup(() => popup(group), { maxWidth: 320 })
        .addTo(markers);
    }

    const t = tally(shown);
    const notMapped = t.total - t.mapped;
    byId("summary").textContent =
      `${t.total} entries match: ${t.mapped} on the map, ${notMapped} not on the map.`;

    const selected = exported.categories.filter((c) => checked.has(c.key));
    const unmapped = byId<HTMLTableElement>("unmapped");
    unmapped.replaceChildren();
    const head = unmapped.createTHead().insertRow();
    head.append(el("th", "Not on the map"), ...selected.map((c) => el("th", c.label, "num")));
    const body = unmapped.createTBody();
    for (const group of UNMAPPED) {
      const row = body.insertRow();
      row.append(el("td", group.label));
      for (const c of selected) {
        const count = tally(shown.filter((r) => r.category === c.key)).unmapped[group.kind];
        row.append(el("td", String(count), "num"));
      }
    }

    const w = wardTable(exported.records, f);
    const wardsTable = byId<HTMLTableElement>("wards");
    wardsTable.replaceChildren();
    const wardHead = wardsTable.createTHead().insertRow();
    wardHead.append(el("th", "Ward"), el("th", "Stops", "num"), el("th", "Crashes", "num"), el("th", "Stops per crash", "num"));
    const wardBody = wardsTable.createTBody();
    for (const row of w.rows) {
      const tr = wardBody.insertRow();
      tr.append(
        el("td", row.ward),
        el("td", String(row.stops), "num"),
        el("td", String(row.crashes), "num"),
        el("td", formatPerCrash(row.stopsPerCrash), "num"),
      );
    }
    const wardStops = w.rows.reduce((sum, row) => sum + row.stops, 0);
    byId("ward-note").textContent =
      `${w.stopsMultiWard.entries} stops sit on a ward boundary and count toward more than one ward, adding ` +
      `${w.stopsMultiWard.extra} extra counts (crashes: ${w.crashesMultiWard.entries}, adding ${w.crashesMultiWard.extra}). ` +
      `${wardStops} ward counts − ${w.stopsMultiWard.extra} extra + ${w.unmappedStops} stops not on the map = ` +
      `${w.totalStops} stops. The date range and Show boxes apply to both columns; the results ticked under Stops to stops only.`;

    const ranking = streetRanking(exported.records, f);
    const rankTable = byId<HTMLTableElement>("ranking");
    rankTable.replaceChildren();
    const rankHead = rankTable.createTHead().insertRow();
    rankHead.append(el("th", "Street"), el("th", "Stops", "num"));
    const rankBody = rankTable.createTBody();
    for (const row of ranking.rows) {
      const tr = rankBody.insertRow();
      tr.append(el("td", row.street), el("td", String(row.stops), "num"));
    }
    byId("ranking-note").textContent =
      `${ranking.countedTwice} intersection stops count toward both streets. ` +
      `Includes stops with a street but no address. Follows the date range, the Stops box and the results ticked under it.`;
  }

  render();
}

void main();
