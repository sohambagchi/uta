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
  segment: (route_id: string, from: string, to: string, date_from?: string) =>
    get<Segment>("/api/segment", { route_id, from, to, date_from }),
  live: () => get<{ as_of: number | null; vehicles: Vehicle[] }>("/api/vehicles/live"),
};
