// Typed client for the FastAPI backend (src/uta/server.py).

export interface Direction {
  direction_id: number;
  headsign: string | null;
  n_stations: number;
}
export interface Route {
  route_id: string;
  route_short_name: string;
  route_long_name: string;
  route_type: number;
  route_color: string | null;
  route_text_color: string | null;
  directions: Direction[];
}
export interface Station {
  seq: number;
  station_id: string;
  name: string;
  lat: number;
  lon: number;
  stop_ids: string[];
  n_trips: number;
}
export type LngLat = [number, number];
export interface RouteDirection {
  direction_id: number;
  headsign: string | null;
  max_trips: number;
  stations: Station[];
  /** Station sequences trips actually run, as indexes into `stations`. */
  patterns: { stations: number[]; n_trips: number }[];
  shape: LngLat[];
}
export interface RouteDetail {
  route: Omit<Route, "directions">;
  directions: RouteDirection[];
}
export interface StationInfo {
  station_id: string;
  name: string;
  lat: number;
  lon: number;
}
/** Observed trips, columnar, oldest first. minute/dow = local departure time. */
export interface Observed {
  depart: number[];
  date: string[];
  dow: number[];
  minute: number[];
  dur: number[];
  sched_dur: (number | null)[];
  dep_delay: (number | null)[];
  trip_id: string[];
  vehicle_id: (string | null)[];
}
/** Timetabled trips, one row per (trip, weekday), weight = number of dates. */
export interface Scheduled {
  minute: number[];
  dow: number[];
  dur: number[];
  weight: number[];
}
export interface Segment {
  route_id: string;
  from: StationInfo;
  to: StationInfo;
  directions: number[];
  stations: (StationInfo & { seq: number; n_trips: number })[];
  geometry: LngLat[];
  observed: Observed;
  scheduled: Scheduled;
}
export interface Vehicle {
  vehicle_id: string;
  ts: number;
  trip_id: string;
  route_id: string | null;
  direction_id: number | null;
  lat: number;
  lon: number;
  bearing: number | null;
  speed: number | null;
  delay_s: number | null;
  next_stop_id: string | null;
  next_stop_name: string | null;
  trip_headsign: string | null;
  route_short_name: string | null;
  route_long_name: string | null;
  route_color: string | null;
  route_type: number | null;
}
export interface NetworkLine {
  route_id: string;
  direction_id: number;
  color: string | null;
  coords: LngLat[];
}
export interface Status {
  gtfs_feed_version: string | null;
  last_poll: { ts: number; error: string | null } | null;
  observed: { first: string | null; last: string | null; n: number; trips: number };
  active_vehicles: number;
  last_ok_poll_age_s: number | null;
}

async function get<T>(path: string, params?: Record<string, string | undefined>): Promise<T> {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params ?? {})) if (v != null && v !== "") q.set(k, v);
  const r = await fetch(path + (q.size ? "?" + q : ""));
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).detail ?? msg; } catch { /* not JSON */ }
    throw new Error(msg);
  }
  return r.json();
}

export const api = {
  status: () => get<Status>("/api/status"),
  routes: () => get<Route[]>("/api/routes"),
  route: (id: string) => get<RouteDetail>(`/api/routes/${encodeURIComponent(id)}`),
  network: () => get<NetworkLine[]>("/api/network"),
  segment: (route_id: string, from: string, to: string, date_from?: string, date_to?: string) =>
    get<Segment>("/api/segment", { route_id, from, to, date_from, date_to }),
  live: () => get<{ as_of: number | null; vehicles: Vehicle[] }>("/api/vehicles/live"),
};

// ---------------------------------------------------------------- insights (dashboard pages)

export type Mode = "bus" | "lrt" | "streetcar" | "rail";
export interface ScopeInfo {
  from: string; to: string; days: string[]; h: [number, number]; modes: Mode[]; dows: number[];
  early_s: number; late_s: number;
}
export interface DelayStats {
  n: number; otp: number | null; early: number | null; late: number | null;
  median: number | null; p10: number | null; p90: number | null;
}
export interface RouteRef { route_id: string; short: string; color: string | null; mode: Mode }
export type Gap = [number, number];
export interface DayInfo { day: number; date: string; origin: number; n: number }

export interface NetworkSummary {
  scope: ScopeInfo;
  origin: number | null;
  kpi: DelayStats & {
    dwell_mean: number | null;
    service: { scheduled: number; observed: number; in_gaps: number };
    vehicles_now: number | null; vehicles_sched_now: number | null; vehicles_at: number | null;
  };
  modes: (DelayStats & { mode: Mode })[];
  mode_hour: { mode: Mode | "all"; h: number; n: number; median: number | null; otp: number | null }[];
  hours: number[];
  routes: (DelayStats & RouteRef & { long: string; text_color: string | null; trips: number; spark: (number | null)[] })[];
  stations: { id: string; name: string; lat: number; lon: number; n: number; median: number }[];
  fleet: { t: number; actual: number; sched: number }[];
  gaps: Gap[];
}

export interface RouteDay {
  scope: ScopeInfo;
  route: { route_id: string; route_short_name: string; route_long_name: string; route_color: string | null;
    route_text_color: string | null; route_type: number; mode: Mode };
  direction_id: number;
  directions: { direction_id: number; headsign: string | null }[];
  feed_version: string | null;
  feeds: { version: string; trips: number; first: string | null; last: string | null }[];
  stations: { station_id: string; name: string; lat: number; lon: number }[];
  kpi: DelayStats & { trips_obs: number; trips_sched: number; rt_obs: number | null; rt_sched: number | null; rt_n: number;
    ewt: number | null; hw_n: number };
  acc: { i: number; n: number; median: number | null; p10: number | null; p90: number | null; dwell: number | null; sdwell: number | null }[];
  runtime: { from: number | null; to: number | null; trips: { t: number; obs: number; sched: number; date: string }[] };
  marey: {
    date: string; origin: number; gaps: Gap[]; no_rt: number[];
    /** obs: [station index, arrival, delay]; sched: [station index, time] */
    trips: { trip_id: string; vehicle: string | null; obs: [number, number, number][]; sched: [number, number][] }[];
    sched_only: { trip_id: string; sched: [number, number][] }[];
  };
  headways: {
    station: number;
    sched: { t: number; observed: boolean }[];
    obs: { t: number; h: number; s: number; spans_missing: boolean }[];
    stats: { n: number; bunched: number; gaps: number; ewt: number | null; cv: number | null; not_seen: number; scheduled: number };
  } | null;
}

export interface StationView {
  scope: ScopeInfo;
  station: { station_id: string; name: string; lat: number; lon: number; n_stops: number };
  origin: number;
  stops: { stop_id: string; name: string; bay: string | null; routes: RouteRef[]; sched: number; observed: number; terminal_only: boolean }[];
  routes: (DelayStats & RouteRef & { direction_id: number; head: string | null; dwell: number | null })[];
  sched_only: (RouteRef & { bay: string | null; bays: string[]; sched: number })[];
  hours: ({ h: number } & Partial<Record<Mode, number>>)[];
  board: (Omit<RouteRef, "route_id"> & { route_id: string; head: string | null; trip_id: string; sched: number; obs: number;
    delay: number; dwell: number | null })[];
  board_until: number;
  served: RouteRef[];
  xfer: { from: string; to: string; events: { from_trip: string; to_trip: string; arr_sched: number; dep_sched: number;
    arr_obs: number | null; dep_obs: number | null; slack_sched: number; slack_obs: number | null }[] } | null;
  gaps: Gap[];
}

export interface TripStop {
  seq: number; stop_id: string; name: string | null; station_id: string | null; sched: number | null; sdwell: number | null;
  timepoint: number | null; obs: number | null; delay: number | null; dwell: number | null; lead: number | null;
  observed: boolean; lat: number | null; lon: number | null;
}
export interface TripView {
  trip: { trip_id: string; route_id: string; short: string | null; long: string | null; color: string | null; mode: Mode | null;
    headsign: string | null; direction_id: number | null; block_id: string | null; date: string; origin: number };
  days: string[];
  vehicles: { vehicle_id: string; t_first: number; t_last: number; seq_first: number; seq_last: number }[];
  stops: TripStop[];
  /** [service-day seconds, lat, lon, speed m/s] */
  gps: [number, number, number, number | null][];
  block_trips: { trip_id: string; route_id: string; short: string | null; start: number }[];
}

export interface VehicleView {
  vehicle_id: string; date: string; origin: number; days: string[]; blocks: string[]; gaps: Gap[];
  trips: { trip_id: string; route_id: string; short: string | null; color: string | null; mode: Mode | null; head: string | null;
    block_id: string | null; sched_start: number | null; sched_end: number | null; obs_start: number | null; obs_end: number | null;
    d_first: number | null; d_last: number | null; n: number; swapped_with: string[]; in_gap: boolean }[];
}

export interface Health {
  scope: ScopeInfo;
  kpi: { last_poll: number | null; polls: number; span_s: number; offline_s: number; uptime: number | null;
    lag_median: number | null; lag_max: number | null; errors: number; error_kinds: [string, number][];
    visits: number; observed: number; rejected: number };
  series: { ts: number[]; veh: (number | null)[]; su: (number | null)[]; lag: (number | null)[]; err: number[] };
  gaps: Gap[];
  coverage: (RouteRef & { sched: number; recorded: number; observed: number; first: number; share: number })[];
  network_share: number | null;
  first_stops: number;
  maturity: { days: number; by_dow: number[]; first: string | null; last: string | null };
}

export interface SearchResult {
  routes: (RouteRef & { long: string })[];
  stations: { station_id: string; name: string; n_stops: number }[];
  trips: string[];
  vehicles: string[];
}

export type ScopeParams = Record<string, string | undefined>;

export const insights = {
  days: () => get<DayInfo[]>("/api/days"),
  network: (s: ScopeParams) => get<NetworkSummary>("/api/insights/network", s),
  route: (id: string, dir: number, s: ScopeParams) =>
    get<RouteDay>(`/api/insights/route/${encodeURIComponent(id)}/${dir}`, s),
  station: (id: string, s: ScopeParams) => get<StationView>(`/api/insights/station/${encodeURIComponent(id)}`, s),
  trip: (id: string, date?: string) => get<TripView>(`/api/insights/trip/${encodeURIComponent(id)}`, { date }),
  vehicle: (id: string, date?: string) => get<VehicleView>(`/api/insights/vehicle/${encodeURIComponent(id)}`, { date }),
  vehicles: (s: ScopeParams) => get<{ vehicle_id: string; trips: number; t_first: number; t_last: number; routes: RouteRef[] }[]>(
    "/api/insights/vehicles", s),
  vehicleGps: (id: string, date?: string) => get<{ vehicle_id: string; date: string; origin: number;
    /** [service-day seconds, lat, lon, speed m/s, trip_id] */ pings: [number, number, number, number | null, string | null][] }>(
    `/api/insights/vehicle/${encodeURIComponent(id)}/gps`, { date }),
  health: (s: ScopeParams) => get<Health>("/api/insights/health", s),
  hubs: () => get<{ station_id: string; name: string; n_stops: number; n_routes: number }[]>("/api/insights/stations"),
  search: (q: string) => get<SearchResult>("/api/search", { q }),
};
