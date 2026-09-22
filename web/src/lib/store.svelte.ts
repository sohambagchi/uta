// App state: comparisons, filters, and caches for routes and segments.
// Comparisons and filters round-trip through the URL hash so views can be bookmarked.

import { api, type Route, type RouteDetail, type Segment } from "./api";
import { denverDaysAgo } from "./format";
import type { Filters } from "./stats";

export const MAX_COMPARISONS = 4;

export interface Comparison {
  id: number;
  slot: number;           // 0..3, fixed for the comparison's life (its color)
  routeId: string | null;
  directionId: number;
  from: string | null;    // station_id
  to: string | null;
}

export type Load<T> = { status: "loading" } | { status: "ok"; data: T } | { status: "error"; error: string };

const DEFAULT_FILTERS: Filters = { range: "30", dows: [], hourFrom: 0, hourTo: 24, trim: true, bin: 60 };

let nextId = 1;

class Store {
  routes = $state<Route[]>([]);
  routeById = $derived(new Map(this.routes.map((r) => [r.route_id, r])));
  details = $state<Record<string, Load<RouteDetail>>>({});
  segments = $state<Record<string, Load<Segment>>>({});
  /** Last loaded segment per comparison, shown dimmed while a refetch is in flight. */
  lastGood = $state<Record<number, Segment>>({});

  comparisons = $state<Comparison[]>([]);
  activeId = $state(0);
  active = $derived(this.comparisons.find((c) => c.id === this.activeId) ?? this.comparisons[0]);
  filters = $state<Filters>({ ...DEFAULT_FILTERS });

  hoverStation = $state<string | null>(null);
  /** Bumped when the map should fit a comparison (id -1 = all of them); {id, n} so repeats re-trigger. */
  focusRequest = $state<{ id: number; n: number } | null>(null);

  // ------------------------------------------------------------ comparisons

  add(init?: Partial<Comparison>): Comparison | undefined {
    if (this.comparisons.length >= MAX_COMPARISONS) return;
    const used = new Set(this.comparisons.map((c) => c.slot));
    const slot = [0, 1, 2, 3].find((s) => !used.has(s))!;
    const c: Comparison = { id: nextId++, slot, routeId: null, directionId: 0, from: null, to: null, ...init };
    this.comparisons.push(c);
    this.activeId = c.id;
    if (c.routeId) this.loadRoute(c.routeId);
    return c;
  }

  remove(id: number) {
    this.comparisons = this.comparisons.filter((c) => c.id !== id);
    if (!this.comparisons.length) this.add();
    if (this.activeId === id) this.activeId = this.comparisons[0].id;
  }

  duplicate(id: number) {
    const c = this.comparisons.find((x) => x.id === id);
    if (c) this.add({ routeId: c.routeId, directionId: c.directionId, from: c.from, to: c.to });
  }

  async setRoute(c: Comparison, routeId: string | null) {
    c.routeId = routeId;
    if (!routeId) { c.from = c.to = null; return; }
    const detail = await this.loadRoute(routeId);
    // keep the stations if the new route serves both, in some direction, in order
    const dir = detail?.directions.find((d) => {
      const i = d.stations.findIndex((s) => s.station_id === c.from);
      const j = d.stations.findIndex((s) => s.station_id === c.to);
      return i >= 0 && j > i;
    });
    if (dir) c.directionId = dir.direction_id;
    else {
      c.from = c.to = null;
      c.directionId = detail?.directions[0]?.direction_id ?? 0;
    }
    this.focus(c.id);
  }

  setDirection(c: Comparison, directionId: number) {
    if (c.directionId === directionId) return;
    c.directionId = directionId;
    c.from = c.to = null;
    this.focus(c.id);
  }

  /** List/map click: first pick is From, second (downstream) is To. */
  pickStation(c: Comparison, stationId: string) {
    const stations = this.direction(c)?.stations ?? [];
    const idx = (id: string | null) => stations.findIndex((s) => s.station_id === id);
    const i = idx(stationId);
    if (i < 0) return;
    if (!c.from || c.to) { c.from = stationId; c.to = null; return; }
    if (stationId === c.from) { c.from = null; return; }
    if (i > idx(c.from)) { c.to = stationId; this.focus(c.id); }
    else c.from = stationId;
  }

  focus(id: number) {
    this.focusRequest = { id, n: (this.focusRequest?.n ?? 0) + 1 };
  }

  // ------------------------------------------------------------ data

  async loadRoutes() {
    this.routes = await api.routes();
  }

  async loadRoute(routeId: string): Promise<RouteDetail | undefined> {
    const cur = this.details[routeId];
    if (cur?.status === "ok") return cur.data;
    if (!cur) {
      this.details[routeId] = { status: "loading" };
      try {
        this.details[routeId] = { status: "ok", data: await api.route(routeId) };
      } catch (e) {
        this.details[routeId] = { status: "error", error: String(e) };
      }
    }
    // another caller started the load; wait for it
    while (this.details[routeId]?.status === "loading") await new Promise((r) => setTimeout(r, 50));
    const done = this.details[routeId];
    return done?.status === "ok" ? done.data : undefined;
  }

  detail(c: Comparison | undefined): RouteDetail | undefined {
    const d = c?.routeId ? this.details[c.routeId] : undefined;
    return d?.status === "ok" ? d.data : undefined;
  }

  direction(c: Comparison | undefined) {
    return this.detail(c)?.directions.find((d) => d.direction_id === c!.directionId);
  }

  dateFrom(): string | undefined {
    return this.filters.range ? denverDaysAgo(+this.filters.range) : undefined;
  }

  segmentKey(c: Comparison): string | null {
    if (!c.routeId || !c.from || !c.to) return null;
    return [c.routeId, c.from, c.to, this.dateFrom() ?? ""].join("|");
  }

  segment(c: Comparison): Load<Segment> | undefined {
    const k = this.segmentKey(c);
    return k ? this.segments[k] : undefined;
  }

  async loadSegment(c: Comparison) {
    const k = this.segmentKey(c);
    if (!k || this.segments[k]) return;
    this.segments[k] = { status: "loading" };
    try {
      const data = await api.segment(c.routeId!, c.from!, c.to!, this.dateFrom());
      this.segments[k] = { status: "ok", data };
      this.lastGood[c.id] = data;
    } catch (e) {
      this.segments[k] = { status: "error", error: String(e) };
    }
  }

  /** Current segment data, or the previous one while loading. */
  segmentData(c: Comparison): Segment | undefined {
    const s = this.segment(c);
    if (s?.status === "ok") return s.data;
    if (s?.status === "loading") return this.lastGood[c.id];
    return undefined;
  }

  /** Drop cached segments so they refetch (new trips since the page loaded). */
  refreshSegments() {
    this.segments = {};
  }

  // ------------------------------------------------------------ URL hash

  toHash(): string {
    const p = new URLSearchParams();
    const cs = this.comparisons.filter((c) => c.routeId)
      .map((c) => [c.routeId, c.directionId, c.from ?? "", c.to ?? ""].join("~"));
    if (cs.length) p.set("c", cs.join(","));
    const f = this.filters;
    if (f.range !== DEFAULT_FILTERS.range) p.set("range", f.range || "all");
    if (f.dows.length) p.set("d", f.dows.join(""));
    if (f.hourFrom !== 0 || f.hourTo !== 24) p.set("h", `${f.hourFrom}-${f.hourTo}`);
    if (!f.trim) p.set("trim", "0");
    if (f.bin !== DEFAULT_FILTERS.bin) p.set("bin", String(f.bin));
    return p.toString();
  }

  fromHash(hash: string) {
    const p = new URLSearchParams(hash.replace(/^#/, ""));
    const f = { ...DEFAULT_FILTERS };
    const range = p.get("range");
    if (range) f.range = range === "all" ? "" : range;
    const d = p.get("d");
    if (d) f.dows = [...d].map(Number).filter((x) => x >= 0 && x < 7);
    const h = p.get("h")?.split("-").map(Number);
    if (h?.length === 2 && h.every(isFinite)) [f.hourFrom, f.hourTo] = h;
    if (p.get("trim") === "0") f.trim = false;
    const bin = Number(p.get("bin"));
    if ([15, 30, 60, 120].includes(bin)) f.bin = bin;
    this.filters = f;

    this.comparisons = [];
    for (const item of (p.get("c") ?? "").split(",").filter(Boolean).slice(0, MAX_COMPARISONS)) {
      const [routeId, dir, from, to] = item.split("~");
      this.add({ routeId, directionId: Number(dir) || 0, from: from || null, to: to || null });
    }
    if (!this.comparisons.length) this.add();
    this.activeId = this.comparisons[0].id;
    if (this.comparisons.some((c) => c.routeId)) this.focus(-1);
  }
}

export const store = new Store();

export function slotColor(slot: number): string {
  return `var(--series-${slot + 1})`;
}
