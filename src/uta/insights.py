"""Query layer for the dashboard pages: network, route-day, station, trip, vehicle, data health.

Most pages aggregate observed stop visits over a scope (a range of service days, weekdays,
hours and modes). Each service day is read once into compact columns (DayFacts) and kept in
memory; a finished day never changes, so its facts are cached until the process ends (LRU),
while the current day is re-read at most every LIVE_TTL_S. Everything else (Marey diagrams,
single trips, vehicles) reads one route, trip or vehicle directly.

Times inside a service day are seconds after that day's origin (GTFS "midnight"), so 25:10
stays 25:10; `origin` is sent alongside when the client needs wall-clock time.
"""

import math
import re
import sqlite3
import statistics
import threading
import time
from array import array
from collections import Counter, OrderedDict, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from . import gps as gpsmod
from .db import EPOCH, OBS_LEAD_MAX, OBS_LEAD_MIN, observed
from .timeutil import service_day_origin

# On-time window at stops: arrival within EARLY_S .. LATE_S of the timetable.
EARLY_S, LATE_S = -60, 300
# A gap between polls longer than this is the collector being offline.
GAP_S = 120
LIVE_TTL_S = 60
CACHE_DAYS = 60
# Timetable stops that aren't passenger stops (driver changeovers), left out of station lists.
NON_PASSENGER = re.compile(r"OPERATOR RELIEF|RELIEF POINT", re.I)
# Statistics with fewer samples than this are not drawn (a hatched cell / gap instead).
MIN_N = 3

MODES = ("bus", "lrt", "streetcar", "rail")
# GTFS gives the S-Line streetcar route_type 0 like TRAX; UTA names it by route number.
STREETCAR_ROUTES = {"720"}


def mode_of(route_type: int | None, short_name: str | None) -> str:
    if route_type == 2:
        return "rail"
    if route_type == 0:
        return "streetcar" if short_name in STREETCAR_ROUTES else "lrt"
    return "bus"


def _in(ids) -> str:
    return ",".join("?" * len(ids))


def day_number(d: str | date) -> int:
    return ((date.fromisoformat(d) if isinstance(d, str) else d) - EPOCH).days


def day_date(day: int) -> date:
    return EPOCH + timedelta(days=day)


def q(xs: list, p: float) -> float | None:
    """Linear-interpolated quantile of an ascending list."""
    if not xs:
        return None
    k = (len(xs) - 1) * p
    lo = math.floor(k)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def delay_stats(delays: list[int]) -> dict:
    """n, on-time share, early/late shares, median and spread of a list of delays (seconds)."""
    n = len(delays)
    if not n:
        return {"n": 0, "otp": None, "early": None, "late": None, "median": None, "p10": None, "p90": None}
    s = sorted(delays)
    early = sum(1 for d in s if d < EARLY_S)
    late = sum(1 for d in s if d > LATE_S)
    return {"n": n, "otp": (n - early - late) / n, "early": early / n, "late": late / n,
            "median": q(s, .5), "p10": q(s, .1), "p90": q(s, .9)}


# ---------------------------------------------------------------- reference data

@dataclass
class Ref:
    """Lookups that only change with a GTFS import: routes, stops -> stations, keys."""
    version: str | None
    routes: dict                     # route_id -> row dict (+ mode)
    route_by_key: dict               # route_keys.key -> route_id
    station_of_stop: dict            # stop_keys.key -> station_id
    stations: dict                   # station_id -> (name, lat, lon)
    stop_name: dict                  # stop_id -> name
    stop_id_by_key: dict             # stop_keys.key -> stop_id
    vehicle_by_key: dict = field(default_factory=dict)


def load_ref(conn: sqlite3.Connection) -> Ref:
    from .db import get_meta
    routes = {}
    for r in conn.execute("SELECT * FROM routes"):
        d = dict(r)
        d["mode"] = mode_of(d["route_type"], d["route_short_name"])
        routes[d["route_id"]] = d
    stations = {r[0]: (r[1], r[2], r[3]) for r in conn.execute("SELECT station_id, name, lat, lon FROM stations")}
    stop_station = dict(conn.execute("SELECT stop_id, station_id FROM stops"))
    stop_id_by_key = dict(conn.execute("SELECT key, stop_id FROM stop_keys"))
    return Ref(
        version=get_meta(conn, "gtfs_feed_version"),
        routes=routes,
        route_by_key=dict(conn.execute("SELECT key, route_id FROM route_keys")),
        station_of_stop={k: stop_station.get(s) for k, s in stop_id_by_key.items()},
        stations=stations,
        stop_name=dict(conn.execute("SELECT stop_id, stop_name FROM stops")),
        stop_id_by_key=stop_id_by_key,
        vehicle_by_key=dict(conn.execute("SELECT key, vehicle_id FROM vehicle_keys")),
    )


# ---------------------------------------------------------------- per-day facts

@dataclass
class DayFacts:
    """Observed visits of one service day as parallel columns, plus per-route counts."""
    day: int
    origin: int
    route: array = field(default_factory=lambda: array("i"))     # route_keys.key
    stop: array = field(default_factory=lambda: array("i"))      # stop_keys.key
    trip: array = field(default_factory=lambda: array("i"))      # trip_dim.key
    arr: array = field(default_factory=lambda: array("i"))       # seconds after origin
    delay: array = field(default_factory=lambda: array("i"))
    dwell: array = field(default_factory=lambda: array("i"))     # -1: unknown
    recorded: Counter = field(default_factory=Counter)           # route key -> visits written
    obs_count: Counter = field(default_factory=Counter)          # route key -> observed visits
    loaded_at: float = 0.0


def read_day(conn: sqlite3.Connection, day: int) -> DayFacts:
    origin = conn.execute("SELECT origin FROM days WHERE day = ?", (day,)).fetchone()
    f = DayFacts(day, origin[0] if origin else service_day_origin(day_date(day)))
    # TODO(perf): visits has no index on day, so this scans the table; fine while history is weeks.
    for route, stop, trip, arr, delay, dwell, lead in conn.execute(
            "SELECT route, stop, trip, arr, delay, dwell, lead_s FROM visits_all WHERE day = ?", (day,)):
        f.recorded[route] += 1
        if lead is None or not OBS_LEAD_MIN <= lead <= OBS_LEAD_MAX:
            continue
        f.obs_count[route] += 1
        if delay is None or arr is None:
            continue
        f.route.append(route)
        f.stop.append(stop)
        f.trip.append(trip)
        f.arr.append(arr)
        f.delay.append(delay)
        f.dwell.append(dwell if dwell is not None and dwell >= 0 else -1)
    f.loaded_at = time.time()
    return f


class Insights:
    """Per-process cache of reference data and day facts over a read-only connection factory."""

    def __init__(self, conn_factory):
        self.conn = conn_factory
        self._lock = threading.Lock()
        self._ref: Ref | None = None
        self._ref_checked = 0.0
        self._days: OrderedDict[int, DayFacts] = OrderedDict()
        self._memo: dict = {}

    # ---- caches

    def ref(self) -> Ref:
        from .db import get_meta
        now = time.time()
        with self._lock:
            if self._ref is None or now - self._ref_checked > 30:
                c = self.conn()
                version = get_meta(c, "gtfs_feed_version")
                keys = c.execute("SELECT (SELECT MAX(key) FROM stop_keys), (SELECT MAX(key) FROM route_keys),"
                                 " (SELECT MAX(key) FROM vehicle_keys)").fetchone()
                if self._ref is None or self._ref.version != version or getattr(self, "_keys", None) != tuple(keys):
                    self._ref = load_ref(c)
                    self._keys = tuple(keys)
                    self._memo.clear()
                self._ref_checked = now
            return self._ref

    def day(self, day: int) -> DayFacts:
        with self._lock:
            f = self._days.get(day)
            if f and (self._finished(f) or time.time() - f.loaded_at < LIVE_TTL_S):
                self._days.move_to_end(day)
                return f
        f = read_day(self.conn(), day)
        with self._lock:
            self._days[day] = f
            self._days.move_to_end(day)
            while len(self._days) > CACHE_DAYS:
                self._days.popitem(last=False)
        return f

    @staticmethod
    def _finished(f: DayFacts) -> bool:
        # the last owl trips of a service day end by ~30 h; visits are final a few minutes later
        return f.loaded_at > f.origin + 31 * 3600

    def memo(self, key, fn, finished: bool):
        """Cache a computed result for finished scopes; recompute others."""
        if finished and key in self._memo:
            return self._memo[key]
        v = fn()
        if finished:
            if len(self._memo) > 500:
                self._memo.clear()
            self._memo[key] = v
        return v

    # ---- scope

    def days_with_data(self) -> list[dict]:
        c = self.conn()
        rows = c.execute(
            """SELECT d.day, d.service_date, d.origin, COALESCE(s.n_observed, 0) AS n
               FROM days d LEFT JOIN day_stats s USING (day) ORDER BY d.day""").fetchall()
        staged = dict(c.execute(f"SELECT day, COUNT(*) FROM visits_new WHERE {observed()} GROUP BY day"))
        return [{"day": r["day"], "date": r["service_date"], "origin": r["origin"], "n": r["n"] + staged.get(r["day"], 0)}
                for r in rows if r["n"] + staged.get(r["day"], 0) > 0]

    def scope(self, date_from: str | None, date_to: str | None, dows: str | None, hours: str | None,
              modes: str | None) -> "Scope":
        days = self.days_with_data()
        # default scope: the whole span of collected data (single-day views use the last day)
        last = days[-1]["day"] if days else day_number(date.today())
        first = days[0]["day"] if days else last
        d1 = day_number(date_to) if date_to else last
        d0 = day_number(date_from) if date_from else (first if not date_to else d1)
        if d0 > d1:
            d0, d1 = d1, d0
        dw = {int(ch) for ch in (dows or "") if ch.isdigit() and int(ch) < 7}
        h0, h1 = 0, 30
        if hours and re.fullmatch(r"\d{1,2}-\d{1,2}", hours):
            h0, h1 = map(int, hours.split("-"))
        ms = {m for m in (modes or "").split(",") if m in MODES} or set(MODES)
        have = {d["day"] for d in days}
        sel = [d for d in range(d0, d1 + 1) if d in have and (not dw or day_date(d).weekday() in dw)]
        return Scope(d0, d1, sel, dw, h0, h1, ms)


@dataclass
class Scope:
    d0: int
    d1: int
    days: list[int]          # days in range with data, after the weekday filter
    dows: set
    h0: int
    h1: int
    modes: set

    def key(self):
        return (self.d0, self.d1, tuple(self.days), tuple(sorted(self.dows)), self.h0, self.h1, tuple(sorted(self.modes)))

    def describe(self) -> dict:
        return {"from": day_date(self.d0).isoformat(), "to": day_date(self.d1).isoformat(),
                "days": [day_date(d).isoformat() for d in self.days], "h": [self.h0, self.h1],
                "modes": sorted(self.modes), "dows": sorted(self.dows), "early_s": EARLY_S, "late_s": LATE_S}


# ---------------------------------------------------------------- collector coverage

def poll_gaps(conn, t0: int, t1: int) -> list[list[int]]:
    """Intervals within [t0, t1) with no poll for more than GAP_S (epoch seconds)."""
    ts = [r[0] for r in conn.execute("SELECT ts FROM polls WHERE ts >= ? AND ts < ? ORDER BY ts", (t0, t1))]
    if not ts:
        return [[t0, t1]]
    out = []
    if ts[0] - t0 > GAP_S:
        out.append([t0, ts[0]])
    out += [[a, b] for a, b in zip(ts, ts[1:]) if b - a > GAP_S]
    if t1 - ts[-1] > GAP_S and t1 < time.time():
        out.append([ts[-1], t1])
    return out


def covered_window(conn, origin: int) -> tuple[int | None, int | None]:
    """First and last poll inside a service day (origin + 3 h .. origin + 29 h)."""
    r = conn.execute("SELECT MIN(ts), MAX(ts) FROM polls WHERE ts >= ? AND ts < ?",
                     (origin + 3 * 3600, origin + 29 * 3600)).fetchone()
    return r[0], r[1]


def scheduled_trips(conn, service_date: str) -> list[tuple]:
    """(trip_id, route_id, direction_id, start_s, end_s) of every trip the current feed runs on a date."""
    return conn.execute(
        """SELECT t.trip_id, t.route_id, COALESCE(t.direction_id, 0), MIN(st.departure_s), MAX(st.arrival_s)
           FROM trips t JOIN service_dates sd ON sd.service_id = t.service_id AND sd.date = ?
           JOIN stop_times st USING (trip_id) GROUP BY t.trip_id""", (service_date,)).fetchall()


# ---------------------------------------------------------------- network

def network_summary(ins: Insights, sc: Scope) -> dict:
    ref = ins.ref()
    conn = ins.conn()
    mode_of_key = {k: ref.routes[r]["mode"] for k, r in ref.route_by_key.items() if r in ref.routes}
    by_mode = defaultdict(list)
    by_mode_hour = defaultdict(list)
    by_route = defaultdict(list)
    by_route_hour = defaultdict(list)
    by_station = defaultdict(list)
    trips_by_route = defaultdict(set)
    dwell_sum = dwell_n = 0
    all_delays = []
    for d in sc.days:
        f = ins.day(d)
        for i in range(len(f.delay)):
            h = f.arr[i] // 3600
            if not sc.h0 <= h < sc.h1:
                continue
            rk = f.route[i]
            m = mode_of_key.get(rk)
            if m is None or m not in sc.modes:
                continue
            dl = f.delay[i]
            all_delays.append(dl)
            by_mode[m].append(dl)
            by_mode_hour[(m, h)].append(dl)
            by_mode_hour[("all", h)].append(dl)
            by_route[rk].append(dl)
            by_route_hour[(rk, h)].append(dl)
            st = ref.station_of_stop.get(f.stop[i])
            if st:
                by_station[st].append(dl)
            trips_by_route[rk].add((d, f.trip[i]))
            if f.dwell[i] >= 0:
                dwell_sum += f.dwell[i]
                dwell_n += 1
    net = delay_stats(all_delays)
    hours = sorted({h for _, h in by_mode_hour})
    routes = []
    for rk, ds in by_route.items():
        r = ref.routes.get(ref.route_by_key[rk])
        if not r:
            continue
        s = delay_stats(ds)
        spark = []
        for h in hours:
            x = by_route_hour.get((rk, h), [])
            spark.append(delay_stats(x)["otp"] if len(x) >= 5 else None)
        routes.append({"route_id": r["route_id"], "short": r["route_short_name"], "long": r["route_long_name"],
                       "color": r["route_color"], "text_color": r["route_text_color"], "mode": r["mode"],
                       "trips": len(trips_by_route[rk]), "spark": spark, **s})
    routes.sort(key=lambda r: (r["otp"] if r["otp"] is not None else 2))
    stations = []
    for sid, ds in by_station.items():
        if len(ds) < 8 or sid not in ref.stations:
            continue
        name, lat, lon = ref.stations[sid]
        ds.sort()
        stations.append({"id": sid, "name": name, "lat": lat, "lon": lon, "n": len(ds), "median": q(ds, .5)})

    # service delivered: scheduled trips that ran while the collector was polling
    service = {"scheduled": 0, "observed": 0, "in_gaps": 0}
    fleet, gaps, origin = [], [], None
    for d in sc.days:
        dd = day_date(d).isoformat()
        f = ins.day(d)
        t_first, t_last = covered_window(conn, f.origin)
        if t_first is None:
            continue
        g = poll_gaps(conn, t_first, min(t_last + 60, int(time.time())))
        observed_trips = {r[0] for r in conn.execute(
            "SELECT t.trip_id FROM trip_days td JOIN trip_dim t ON t.key = td.trip WHERE td.day = ? AND td.n_observed > 0",
            (d,))} | {r[0] for r in conn.execute(
                f"SELECT DISTINCT t.trip_id FROM visits_new v JOIN trip_dim t ON t.key = v.trip WHERE v.day = ? AND {observed('v')}",
                (d,))}
        sched = scheduled_trips(conn, dd)
        for trip_id, route_id, _dir, s0, s1 in sched:
            r = ref.routes.get(route_id)
            if not r or r["mode"] not in sc.modes or s0 is None:
                continue
            a, b = f.origin + s0, f.origin + s1
            if a < t_first + 600 or b > t_last - 300 or not sc.h0 <= s0 // 3600 < sc.h1:
                continue          # not fully inside the collected window
            if any(g0 < b and g1 > a for g0, g1 in g):
                if trip_id not in observed_trips:
                    service["in_gaps"] += 1
                continue
            service["scheduled"] += 1
            service["observed"] += trip_id in observed_trips
        if d == sc.d1:
            origin = f.origin
            gaps = [[a - f.origin, b - f.origin] for a, b in g]
            fleet = [x for x in fleet_curve(conn, d, f.origin, t_first, t_last, sched, ref, sc.modes)
                     if sc.h0 * 3600 <= x["t"] <= sc.h1 * 3600]
    now_row = fleet[-1] if fleet else None
    return {
        "scope": sc.describe(),
        "origin": origin,
        "kpi": {**net, "dwell_mean": dwell_sum / dwell_n if dwell_n else None, "service": service,
                "vehicles_now": now_row["actual"] if now_row else None,
                "vehicles_sched_now": now_row["sched"] if now_row else None,
                "vehicles_at": now_row["t"] if now_row else None},
        "modes": [{"mode": m, **delay_stats(by_mode[m])} for m in MODES if m in by_mode],
        "mode_hour": [{"mode": m, "h": h, **{k: v for k, v in delay_stats(x).items() if k in ("n", "median", "otp")}}
                      for (m, h), x in sorted(by_mode_hour.items(), key=lambda kv: (kv[0][0], kv[0][1]))],
        "hours": hours,
        "routes": routes,
        "stations": stations,
        "fleet": fleet,
        "gaps": gaps,
    }


FLEET_STEP_S = 600
FLEET_WINDOW_S = 60     # a vehicle counts at time t if it pinged on a trip within t +/- this


def fleet_curve(conn, day: int, origin: int, t_first: int, t_last: int, sched, ref: Ref, modes: set) -> list[dict]:
    """Vehicles reporting a trip (GPS) vs trips the timetable has running, every 10 minutes
    (service-day seconds)."""
    trip_route = dict(conn.execute("SELECT key, route_id FROM gps_trips"))
    keep = {k for k, rid in trip_route.items() if ref.routes.get(rid, {}).get("mode") in modes}
    step, w = FLEET_STEP_S, FLEET_WINDOW_S
    t = (t_first - origin) // step * step + step
    end = min(t_last, int(time.time())) - origin
    buckets = defaultdict(set)
    lo, hi = origin + t - w, origin + end + w + 1

    def add(ts, vehicle, trip):
        if trip in keep:
            k = round((ts - origin) / step) * step
            if abs(ts - origin - k) <= w:
                buckets[k].add(vehicle)

    for vehicle, data in conn.execute("SELECT vehicle, data FROM gps_blocks WHERE t_last >= ? AND t_first < ?", (lo, hi)):
        for p in gpsmod.decode(data):
            if lo <= p[0] < hi:
                add(p[0], vehicle, p[1])
    for ts, vehicle, trip in conn.execute(
            "SELECT ts, vehicle, trip FROM gps_recent WHERE ts >= ? AND ts < ? AND trip IS NOT NULL", (lo, hi)):
        add(ts, vehicle, trip)
    sched = [(s0, s1) for _, rid, _, s0, s1 in sched
             if s0 is not None and ref.routes.get(rid, {}).get("mode") in modes]
    out = []
    while t <= end:
        out.append({"t": t, "actual": len(buckets.get(t, ())), "sched": sum(1 for a, b in sched if a <= t <= b)})
        t += step
    return out


# ---------------------------------------------------------------- route (one direction)

def route_day(ins: Insights, sc: Scope, route_id: str, direction_id: int, at: str | None) -> dict | None:
    ref = ins.ref()
    conn = ins.conn()
    r = ref.routes.get(route_id)
    if r is None:
        return None
    stations = [dict(x) for x in conn.execute(
        """SELECT rs.seq, rs.station_id, st.name, st.lat, st.lon, rs.stop_ids FROM route_stops rs
           JOIN stations st USING (station_id) WHERE rs.route_id = ? AND rs.direction_id = ? ORDER BY rs.seq""",
        (route_id, direction_id)) if not NON_PASSENGER.search(x["name"] or "")]
    idx = {s["station_id"]: i for i, s in enumerate(stations)}
    directions = [{"direction_id": d, "headsign": h} for d, h in conn.execute(
        """SELECT COALESCE(direction_id, 0) AS d,
                  (SELECT trip_headsign FROM trips t2 WHERE t2.route_id = t.route_id AND COALESCE(t2.direction_id, 0)
                   = COALESCE(t.direction_id, 0) GROUP BY trip_headsign ORDER BY COUNT(*) DESC LIMIT 1)
           FROM trips t WHERE route_id = ? GROUP BY d ORDER BY d""", (route_id,))]
    rk = conn.execute("SELECT key FROM route_keys WHERE route_id = ?", (route_id,)).fetchone()
    trip_dir = {k: dr for k, dr in conn.execute(
        "SELECT key, COALESCE(direction_id, 0) FROM trip_dim WHERE route_id = ?", (route_id,))}
    trip_ids = dict(conn.execute("SELECT key, trip_id FROM trip_dim WHERE route_id = ?", (route_id,)))

    # visits of this route and direction over the scope, per station
    per_station = defaultdict(list)       # i -> delays
    dwell = defaultdict(list)
    sdwell = defaultdict(list)
    trips_obs = set()
    runs = defaultdict(dict)              # (day, trip) -> {i: (arr, delay, dwell, sched_dwell)}
    marey_day = sc.d1
    marey = defaultdict(list)             # trip key -> [(i, arr, sched, delay, vehicle)]
    if rk:
        for day, trip, stop, arr, delay, dw, sdw, lead, veh in conn.execute(
                f"""SELECT day, trip, stop, arr, delay, dwell, sched_dwell, lead_s, vehicle FROM visits_all
                    WHERE route = ? AND day BETWEEN ? AND ?""", (rk[0], sc.d0, sc.d1)):
            if trip_dir.get(trip) != direction_id or day not in sc.days and day != marey_day:
                continue
            i = idx.get(ref.station_of_stop.get(stop))
            if i is None:
                continue
            obs = lead is not None and OBS_LEAD_MIN <= lead <= OBS_LEAD_MAX
            if day == marey_day:
                marey[trip].append((i, arr if obs else None, arr - delay if delay is not None and arr is not None else None,
                                    delay if obs else None, veh))
            if day not in sc.days or not obs or delay is None or not sc.h0 <= arr // 3600 < sc.h1:
                continue
            per_station[i].append(delay)
            trips_obs.add((day, trip))
            if dw is not None:
                dwell[i].append(dw)
            if sdw is not None:
                sdwell[i].append(sdw)
            runs[(day, trip)][i] = (arr, delay, dw, sdw)

    acc = []
    for i in range(len(stations)):
        s = delay_stats(per_station[i])
        dw_ = sorted(dwell[i])
        sd_ = sorted(sdwell[i])
        acc.append({"i": i, "n": s["n"], "median": s["median"], "p10": s["p10"], "p90": s["p90"],
                    "dwell": q(dw_, .5), "sdwell": q(sd_, .5)})
    all_d = [x for v in per_station.values() for x in v]
    kpi = delay_stats(all_d)

    # running time between the outermost stations most trips are observed at
    counts = [a["n"] for a in acc]
    runtime = {"from": None, "to": None, "trips": []}
    if counts and max(counts) > 0:
        good = [i for i, c in enumerate(counts) if c >= 0.5 * max(counts)]
        a, b = good[0], good[-1]
        if b > a:
            runtime.update({"from": a, "to": b})
            for (day, trip), vis in runs.items():
                if a in vis and b in vis:
                    (arr_a, d_a, dw_a, sdw_a), (arr_b, d_b, _, _) = vis[a], vis[b]
                    dep = arr_a + (dw_a or 0)
                    sdep = arr_a - d_a + (sdw_a or 0)
                    runtime["trips"].append({"t": sdep, "obs": arr_b - dep, "sched": (arr_b - d_b) - sdep,
                                             "date": day_date(day).isoformat()})
            runtime["trips"].sort(key=lambda x: x["t"])
    rt_obs = sorted(x["obs"] for x in runtime["trips"])
    rt_sched = sorted(x["sched"] for x in runtime["trips"])

    # Marey (single day): observed and timetable per trip
    md = day_date(marey_day).isoformat()
    origin_row = conn.execute("SELECT origin FROM days WHERE day = ?", (marey_day,)).fetchone()
    origin = origin_row[0] if origin_row else service_day_origin(day_date(marey_day))
    sched_trips = defaultdict(list)
    for trip_id, stop_id, arr_s in conn.execute(
            """SELECT t.trip_id, st.stop_id, st.arrival_s FROM trips t
               JOIN service_dates sd ON sd.service_id = t.service_id AND sd.date = ?
               JOIN stop_times st USING (trip_id)
               WHERE t.route_id = ? AND COALESCE(t.direction_id, 0) = ? ORDER BY t.trip_id, st.stop_sequence""",
            (md, route_id, direction_id)):
        i = idx.get(_station_of_stop_id(conn, ref, stop_id))
        if i is not None and arr_s is not None:
            sched_trips[trip_id].append([i, arr_s])
    observed_ids = set()
    m_trips = []
    for trip, pts in marey.items():
        pts.sort(key=lambda p: p[0])
        tid = trip_ids.get(trip)
        observed_ids.add(tid)
        veh = next((ref.vehicle_by_key.get(p[4]) for p in pts if p[4]), None)
        m_trips.append({"trip_id": tid, "vehicle": veh,
                        "obs": [[p[0], p[1], p[3]] for p in pts if p[1] is not None],
                        "sched": [[p[0], p[2]] for p in pts if p[2] is not None]})
    sched_only = [{"trip_id": t, "sched": pts} for t, pts in sched_trips.items() if t not in observed_ids]
    for m in m_trips:
        if len(m["sched"]) < 2 and m["trip_id"] in sched_trips:
            m["sched"] = sched_trips[m["trip_id"]]
    t_first, t_last = covered_window(conn, origin)
    gaps = [[a - origin, b - origin] for a, b in poll_gaps(conn, t_first, min(t_last + 60, int(time.time())))] \
        if t_first else []

    # headways at one station (default: the busiest with realtime)
    hw_i = idx.get(at) if at else None
    if hw_i is None and counts and max(counts) > 0:
        mid = [i for i, c in enumerate(counts) if c >= 0.8 * max(counts)]
        hw_i = mid[len(mid) // 2]
    # headways over the polled part of the day, narrowed to the scope's hours
    window = (max(t_first - origin, sc.h0 * 3600), min(t_last - origin, sc.h1 * 3600)) if t_first else None
    headways = headway_stats(m_trips, sched_trips, hw_i, window, gaps) if hw_i is not None else None

    def polled(a, b):
        return window and a < window[1] and b > window[0] and not any(g0 <= a and b <= g1 for g0, g1 in gaps)
    trips_sched = sum(1 for pts in sched_trips.values() if polled(pts[0][1], pts[-1][1]))
    return {
        "scope": sc.describe(),
        "route": {k: r[k] for k in ("route_id", "route_short_name", "route_long_name", "route_color",
                                    "route_text_color", "route_type", "mode")},
        "direction_id": direction_id,
        "directions": directions,
        "feed_version": ref.version,
        "feeds": [{"version": v, "trips": n, "first": day_date(a).isoformat() if a is not None else None,
                   "last": day_date(b).isoformat() if b is not None else None}
                  for v, n, a, b in conn.execute(
                      """SELECT t.feed_version, COUNT(DISTINCT t.key), MIN(td.day), MAX(td.day) FROM trip_dim t
                         LEFT JOIN trip_days td ON td.trip = t.key
                         WHERE t.route_id = ? AND COALESCE(t.direction_id, 0) = ? GROUP BY t.feed_version ORDER BY 3""",
                      (route_id, direction_id))],
        "stations": [{"station_id": s["station_id"], "name": s["name"], "lat": s["lat"], "lon": s["lon"]} for s in stations],
        "kpi": {**kpi, "trips_obs": len(trips_obs), "trips_sched": trips_sched,
                "rt_obs": q(rt_obs, .5), "rt_sched": q(rt_sched, .5), "rt_n": len(rt_obs),
                "ewt": headways["stats"]["ewt"] if headways else None,
                "hw_n": headways["stats"]["n"] if headways else 0},
        "acc": acc,
        "runtime": runtime,
        "marey": {"date": md, "origin": origin, "trips": m_trips, "sched_only": sched_only, "gaps": gaps,
                  # stations never observed on the Marey day (terminals UTA publishes no realtime for)
                  "no_rt": [i for i in range(len(stations)) if not any(p[0] == i for m in m_trips for p in m["obs"])]},
        "headways": headways,
    }


def _station_of_stop_id(conn, ref: Ref, stop_id: str):
    # ref maps stop keys; the timetable uses stop ids
    cache = getattr(ref, "_station_by_stop_id", None)
    if cache is None:
        cache = dict(conn.execute("SELECT stop_id, station_id FROM stops"))
        ref._station_by_stop_id = cache
    return cache.get(stop_id)


def headway_stats(m_trips, sched_trips, i: int, window, outages) -> dict:
    """Gaps between consecutive observed arrivals at station i on the Marey day, against the
    timetable. A gap that spans a scheduled arrival we did not observe is excluded: a missing
    observation is not a missing vehicle."""
    obs = sorted((p[1], p[1] - p[2]) for m in m_trips for p in m["obs"] if p[0] == i and p[2] is not None
                 and (not window or window[0] <= p[1] <= window[1]))
    sched = sorted(t for pts in sched_trips.values() for j, t in pts if j == i
                   and window and window[0] <= t <= window[1] and not any(g0 <= t <= g1 for g0, g1 in outages))
    obs_sched = [s for _, s in obs]
    sched_marked = [{"t": s, "observed": any(abs(s - o) < 90 for o in obs_sched)} for s in sched]
    unseen = [s["t"] for s in sched_marked if not s["observed"]]
    gaps = []
    for (a, sa), (b, sb) in zip(obs, obs[1:]):
        h, s = b - a, sb - sa
        # a gap that spans an unobserved arrival or a collector outage says nothing about spacing
        spans = any(sa < u < sb for u in unseen) or any(g0 < b and g1 > a for g0, g1 in outages)
        gaps.append({"t": b, "h": h, "s": s, "spans_missing": spans})
    clean = [g for g in gaps if not g["spans_missing"] and g["s"] > 0]
    H = [g["h"] for g in clean]
    S = [g["s"] for g in clean]
    stats = {"n": len(clean), "bunched": sum(g["h"] < g["s"] / 4 for g in clean),
             "gaps": sum(g["h"] > 1.5 * g["s"] for g in clean),
             "ewt": (sum(h * h for h in H) / (2 * sum(H)) - sum(s * s for s in S) / (2 * sum(S))) if H else None,
             "cv": (statistics.pstdev(H) / statistics.mean(H)) if len(H) > 1 else None,
             "not_seen": len(unseen), "scheduled": len(sched)}
    return {"station": i, "sched": sched_marked, "obs": gaps, "stats": stats}


# ---------------------------------------------------------------- station

BAY = re.compile(r"\((Bay [^)]+)\)")


def station_view(ins: Insights, sc: Scope, station_id: str, board_until: int | None,
                 xf: str | None, xt: str | None) -> dict | None:
    ref = ins.ref()
    conn = ins.conn()
    st = conn.execute("SELECT * FROM stations WHERE station_id = ?", (station_id,)).fetchone()
    if st is None:
        return None
    stops = [dict(r) for r in conn.execute("SELECT stop_id, stop_name FROM stops WHERE station_id = ?", (station_id,))]
    stop_ids = [s["stop_id"] for s in stops]
    keys = dict(conn.execute(f"SELECT key, stop_id FROM stop_keys WHERE stop_id IN ({_in(stop_ids)})", stop_ids))
    day = sc.d1
    dd = day_date(day).isoformat()
    origin_row = conn.execute("SELECT origin FROM days WHERE day = ?", (day,)).fetchone()
    origin = origin_row[0] if origin_row else service_day_origin(day_date(day))

    # timetable at each stop on the last day: arrivals, and whether they are all first/last stops
    sched = defaultdict(lambda: {"n": 0, "terminal": 0, "routes": set(), "by_route": Counter()})
    sched_rows = []
    t_first, t_last = covered_window(conn, origin)
    for stop_id, trip_id, route_id, dir_, head, seq, arr_s, dep_s, first, last in conn.execute(
            f"""SELECT st.stop_id, st.trip_id, t.route_id, COALESCE(t.direction_id, 0), t.trip_headsign,
                       st.stop_sequence, st.arrival_s, st.departure_s,
                       st.stop_sequence = (SELECT MIN(stop_sequence) FROM stop_times x WHERE x.trip_id = st.trip_id),
                       st.stop_sequence = (SELECT MAX(stop_sequence) FROM stop_times x WHERE x.trip_id = st.trip_id)
                FROM stop_times st JOIN trips t USING (trip_id)
                JOIN service_dates sd ON sd.service_id = t.service_id AND sd.date = ?
                WHERE st.stop_id IN ({_in(stop_ids)})""", [dd, *stop_ids]):
        s = sched[stop_id]
        s["n"] += 1
        s["terminal"] += bool(first or last)
        s["routes"].add(route_id)
        s["by_route"][route_id] += 1
        sched_rows.append((stop_id, trip_id, route_id, dir_, head, arr_s, dep_s))

    # observed visits over the scope
    rows = []
    for d in sc.days:
        f = ins.day(d)
        for i in range(len(f.stop)):
            if f.stop[i] in keys:
                rows.append((d, i, f))
    per_route = defaultdict(lambda: {"delays": [], "dwell": []})
    hours = defaultdict(Counter)
    trip_info = {}
    need = {f.trip[i] for _, i, f in rows}
    if need:
        for k, tid, rid, dr, head in conn.execute(
                f"SELECT key, trip_id, route_id, COALESCE(direction_id, 0), trip_headsign FROM trip_dim WHERE key IN ({_in(need)})",
                list(need)):
            trip_info[k] = (tid, rid, dr, head)
    obs_by_stop = Counter()
    board = []
    for d, i, f in rows:
        tid, rid, dr, head = trip_info.get(f.trip[i], (None, None, 0, None))
        r = ref.routes.get(rid)
        if not r or r["mode"] not in sc.modes:
            continue
        h = f.arr[i] // 3600
        obs_by_stop[keys[f.stop[i]]] += 1
        if sc.h0 <= h < sc.h1:
            g = per_route[(rid, dr, head)]
            g["delays"].append(f.delay[i])
            if f.dwell[i] >= 0:
                g["dwell"].append(f.dwell[i])
            if d == day:
                hours[h][r["mode"]] += 1
        if d == day and sc.h0 <= h < sc.h1:
            board.append({"route_id": rid, "short": r["route_short_name"], "color": r["route_color"], "mode": r["mode"],
                          "head": head, "trip_id": tid, "sched": f.arr[i] - f.delay[i], "obs": f.arr[i],
                          "delay": f.delay[i], "dwell": f.dwell[i] if f.dwell[i] >= 0 else None})
    board.sort(key=lambda b: b["obs"])
    until = board_until if board_until is not None else (board[-1]["obs"] + 1 if board else 0)
    board = [b for b in board if b["obs"] <= until][-14:]

    route_rows = []
    for (rid, dr, head), g in per_route.items():
        r = ref.routes[rid]
        s = delay_stats(g["delays"])
        dw = sorted(g["dwell"])
        route_rows.append({"route_id": rid, "short": r["route_short_name"], "color": r["route_color"],
                           "mode": r["mode"], "direction_id": dr, "head": head, **s, "dwell": q(dw, .5)})
    route_rows.sort(key=lambda x: (MODES.index(x["mode"]) if x["mode"] != "bus" else 9, x["short"], x["direction_id"]))

    stop_rows = []
    for s in stops:
        sd = sched.get(s["stop_id"], {"n": 0, "terminal": 0, "routes": set()})
        bay = BAY.search(s["stop_name"] or "")
        rts = sorted(sd["routes"], key=lambda rid: (ref.routes.get(rid, {}).get("route_type", 3) == 3,
                                                   ref.routes.get(rid, {}).get("route_short_name", "")))
        stop_rows.append({"stop_id": s["stop_id"], "name": s["stop_name"], "bay": bay.group(1) if bay else None,
                          "routes": [{"route_id": x, "short": ref.routes[x]["route_short_name"],
                                      "color": ref.routes[x]["route_color"], "mode": ref.routes[x]["mode"]} for x in rts if x in ref.routes],
                          "sched": sd["n"], "observed": obs_by_stop.get(s["stop_id"], 0),
                          "terminal_only": sd["n"] > 0 and sd["terminal"] == sd["n"]})
    stop_rows.sort(key=lambda x: (x["bay"] is not None, x["bay"] or "", -x["sched"]))
    # routes seen here only as terminal stops (no realtime)
    # one row per route, its scheduled arrivals summed over the bays where it starts or ends
    only: dict = {}
    seen_routes = {rid for rid, _, _ in per_route}
    for s in stop_rows:
        if s["terminal_only"]:
            for rt in s["routes"]:
                if rt["route_id"] in seen_routes or rt["mode"] not in sc.modes:
                    continue
                n = sched[s["stop_id"]]["by_route"][rt["route_id"]]
                row = only.setdefault(rt["route_id"], {**rt, "bays": [], "sched": 0})
                row["sched"] += n
                if s["bay"]:
                    row["bays"].append(s["bay"])
    sched_only = [{**r, "bay": ", ".join(r["bays"]) or None} for r in only.values()]

    # transfer check on the last day: arrivals of route xf, next departure of route xt
    served = sorted({x[2] for x in sched_rows}, key=lambda rid: ref.routes.get(rid, {}).get("route_short_name", ""))
    if not (xf and xt):
        rail = [rid for rid in served if ref.routes.get(rid, {}).get("mode") == "rail"]
        lrt = [rid for rid in served if ref.routes.get(rid, {}).get("mode") in ("lrt", "streetcar")]
        if rail and lrt:
            xf, xt = rail[0], lrt[0]
        elif len(lrt) >= 2:
            xf, xt = lrt[0], lrt[1]
        elif len(served) >= 2:
            xf, xt = served[0], served[1]
    xfer = transfer_check(conn, ref, day, origin, keys, sched_rows, xf, xt) if xf and xt else None
    if xfer:
        xfer["events"] = [e for e in xfer["events"] if sc.h0 * 3600 <= e["arr_sched"] < sc.h1 * 3600]

    gaps = [[a - origin, b - origin] for a, b in poll_gaps(conn, t_first, min(t_last + 60, int(time.time())))] \
        if t_first else []
    return {
        "scope": sc.describe(),
        "station": {"station_id": station_id, "name": st["name"], "lat": st["lat"], "lon": st["lon"], "n_stops": st["n_stops"]},
        "origin": origin,
        "stops": stop_rows,
        "routes": route_rows,
        "sched_only": sched_only,
        "hours": [{"h": h, **dict(c)} for h, c in sorted(hours.items())],
        "board": board,
        "board_until": until,
        "served": [{"route_id": x, "short": ref.routes[x]["route_short_name"], "color": ref.routes[x]["route_color"],
                    "mode": ref.routes[x]["mode"]} for x in served if x in ref.routes],
        "xfer": xfer,
        "gaps": gaps,
    }


def transfer_check(conn, ref: Ref, day: int, origin: int, keys: dict, sched_rows, xf: str, xt: str) -> dict:
    """For each scheduled arrival of route xf, the next scheduled departure of route xt 3-15 min
    later, and whether the connection held in what was observed."""
    obs = {}
    stop_keys = list(keys)
    if stop_keys:
        for trip_id, arr, delay, dwell, sdwell, lead in conn.execute(
                f"""SELECT t.trip_id, v.arr, v.delay, v.dwell, v.sched_dwell, v.lead_s FROM visits_all v
                    JOIN trip_dim t ON t.key = v.trip
                    WHERE v.stop IN ({_in(stop_keys)}) AND v.day = ? AND t.route_id IN (?, ?)""",
                [*stop_keys, day, xf, xt]):
            ok = lead is not None and OBS_LEAD_MIN <= lead <= OBS_LEAD_MAX
            obs[trip_id] = (arr if ok else None, (arr + (dwell or 0)) if ok else None)
    arrivals = sorted((a, tid, dr) for _, tid, rid, dr, _, a, _ in sched_rows if rid == xf and a is not None)
    departures = sorted((dp, tid, dr) for _, tid, rid, dr, _, _, dp in sched_rows if rid == xt and dp is not None)
    events = []
    for a, tid, dr in arrivals:
        nxt = next(((dp, t2, d2) for dp, t2, d2 in departures if 180 <= dp - a <= 900), None)
        if not nxt:
            continue
        dp, t2, _ = nxt
        oa = obs.get(tid, (None, None))[0]
        od = obs.get(t2, (None, None))[1]
        events.append({"from_trip": tid, "to_trip": t2, "arr_sched": a, "dep_sched": dp,
                       "arr_obs": oa, "dep_obs": od, "slack_sched": dp - a,
                       "slack_obs": (od - oa) if oa is not None and od is not None else None})
    return {"from": xf, "to": xt, "events": events}


# ---------------------------------------------------------------- trip

def trip_view(ins: Insights, trip_id: str, service_date: str | None) -> dict | None:
    ref = ins.ref()
    conn = ins.conn()
    dims = conn.execute("SELECT * FROM trip_dim WHERE trip_id = ? ORDER BY key DESC", (trip_id,)).fetchall()
    static = conn.execute("SELECT * FROM trips WHERE trip_id = ?", (trip_id,)).fetchone()
    if not dims and static is None:
        return None
    info = dict(dims[0]) if dims else dict(static)
    route_id = info["route_id"]
    r = ref.routes.get(route_id, {})
    keys = [d["key"] for d in dims]
    days = []
    if keys:
        days = [x[0] for x in conn.execute(
            f"SELECT DISTINCT day FROM trip_days WHERE trip IN ({_in(keys)}) ORDER BY day", keys)]
        days += [x[0] for x in conn.execute(
            f"SELECT DISTINCT day FROM visits_new WHERE trip IN ({_in(keys)})", keys) if x[0] not in days]
        days.sort()
    day = day_number(service_date) if service_date else (days[-1] if days else day_number(date.today()))
    origin_row = conn.execute("SELECT origin FROM days WHERE day = ?", (day,)).fetchone()
    origin = origin_row[0] if origin_row else service_day_origin(day_date(day))

    # timetable (current feed) and observed visits, merged by stop_sequence
    stops = {}
    for seq, stop_id, arr_s, dep_s, tp in conn.execute(
            "SELECT stop_sequence, stop_id, arrival_s, departure_s, timepoint FROM stop_times WHERE trip_id = ? ORDER BY stop_sequence",
            (trip_id,)):
        stops[seq] = {"seq": seq, "stop_id": stop_id, "name": ref.stop_name.get(stop_id),
                      "station_id": _station_of_stop_id(conn, ref, stop_id), "sched": arr_s,
                      "sdwell": (dep_s - arr_s) if dep_s is not None and arr_s is not None else None,
                      "timepoint": tp, "obs": None, "delay": None, "dwell": None, "lead": None, "observed": False}
    vehicles = []
    rk = conn.execute("SELECT key FROM route_keys WHERE route_id = ?", (route_id,)).fetchone()
    if rk and keys:
        for seq, stop, arr, delay, dwell, sdwell, lead, veh in conn.execute(
                f"""SELECT seq, stop, arr, delay, dwell, sched_dwell, lead_s, vehicle FROM visits_all
                    WHERE route = ? AND day = ? AND trip IN ({_in(keys)})""", [rk[0], day, *keys]):
            stop_id = ref.stop_id_by_key.get(stop)
            s = stops.setdefault(seq, {"seq": seq, "stop_id": stop_id, "name": ref.stop_name.get(stop_id),
                                       "station_id": _station_of_stop_id(conn, ref, stop_id),
                                       "sched": arr - delay if delay is not None and arr is not None else None,
                                       "sdwell": sdwell, "timepoint": None})
            ok = lead is not None and OBS_LEAD_MIN <= lead <= OBS_LEAD_MAX
            s.update({"obs": arr if ok else None, "delay": delay if ok else None, "dwell": dwell if ok else None,
                      "lead": lead, "observed": ok})
    for vk, t0, t1, s0, s1 in conn.execute(
            f"SELECT vehicle, t_first, t_last, seq_first, seq_last FROM trip_vehicle WHERE day = ? AND trip IN ({_in(keys)}) ORDER BY t_first",
            [day, *keys]) if keys else []:
        vehicles.append({"vehicle_id": ref.vehicle_by_key.get(vk), "t_first": t0, "t_last": t1, "seq_first": s0, "seq_last": s1})
    stop_list = [stops[k] for k in sorted(stops) if not NON_PASSENGER.search(stops[k]["name"] or "")]
    for s in stop_list:
        st = ref.stations.get(s.get("station_id"))
        s["lat"], s["lon"] = (st[1], st[2]) if st else (None, None)

    # GPS of the vehicle(s) while on this trip (plus a little either side)
    pings = []
    sched_times = [s["sched"] for s in stop_list if s["sched"] is not None]
    if vehicles and sched_times:
        t0 = min(vehicles[0]["t_first"], origin + sched_times[0]) - 300
        t1 = max(vehicles[-1]["t_last"], origin + sched_times[-1]) + 900
        for v in {v["vehicle_id"] for v in vehicles}:
            for ts, lat, lon, speed, bearing in vehicle_pings(conn, v, t0, t1):
                pings.append([ts - origin, lat, lon, speed])
        pings.sort()

    # other trips of the same block that day
    block = info.get("block_id")
    block_trips = []
    if block:
        block_trips = [{"trip_id": t, "route_id": rid, "short": ref.routes.get(rid, {}).get("route_short_name"),
                        "start": s0} for t, rid, s0 in conn.execute(
            """SELECT t.trip_id, t.route_id, MIN(st.departure_s) FROM trips t
               JOIN service_dates sd ON sd.service_id = t.service_id AND sd.date = ?
               JOIN stop_times st USING (trip_id) WHERE t.block_id = ? GROUP BY t.trip_id ORDER BY 3""",
            (day_date(day).isoformat(), block))]
    return {
        "trip": {"trip_id": trip_id, "route_id": route_id, "short": r.get("route_short_name"),
                 "long": r.get("route_long_name"), "color": r.get("route_color"), "mode": r.get("mode"),
                 "headsign": info.get("trip_headsign"), "direction_id": info.get("direction_id"),
                 "block_id": block, "date": day_date(day).isoformat(), "origin": origin},
        "days": [day_date(d).isoformat() for d in days],
        "vehicles": vehicles,
        "stops": stop_list,
        "gps": pings,
        "block_trips": block_trips,
    }


def vehicle_pings(conn, vehicle_id: str, t0: int, t1: int) -> list[tuple]:
    """(ts, lat, lon, speed, bearing) of one vehicle in [t0, t1), from sealed blocks and recent pings."""
    vk = conn.execute("SELECT key FROM vehicle_keys WHERE vehicle_id = ?", (vehicle_id,)).fetchone()
    if vk is None:
        return []
    out = []
    for (data,) in conn.execute("SELECT data FROM gps_blocks WHERE vehicle = ? AND t_last >= ? AND t_first < ?",
                                (vk[0], t0, t1)):
        out += [(p[0], p[3], p[4], p[6], p[5]) for p in gpsmod.decode(data) if t0 <= p[0] < t1]
    out += [tuple(r) for r in conn.execute(
        "SELECT ts, lat, lon, speed, bearing FROM gps_recent WHERE ts >= ? AND ts < ? AND vehicle = ?", (t0, t1, vk[0]))]
    out.sort()
    return out


# ---------------------------------------------------------------- vehicle

def vehicle_view(ins: Insights, vehicle_id: str, service_date: str | None) -> dict | None:
    ref = ins.ref()
    conn = ins.conn()
    vk = conn.execute("SELECT key FROM vehicle_keys WHERE vehicle_id = ?", (vehicle_id,)).fetchone()
    if vk is None:
        return None
    days = [x[0] for x in conn.execute("SELECT DISTINCT day FROM trip_vehicle WHERE vehicle = ? ORDER BY day", (vk[0],))]
    day = day_number(service_date) if service_date else (days[-1] if days else day_number(date.today()))
    origin_row = conn.execute("SELECT origin FROM days WHERE day = ?", (day,)).fetchone()
    origin = origin_row[0] if origin_row else service_day_origin(day_date(day))
    rows = conn.execute(
        """SELECT tv.trip, tv.t_first, tv.t_last, t.trip_id, t.route_id, t.trip_headsign, t.block_id
           FROM trip_vehicle tv JOIN trip_dim t ON t.key = tv.trip
           WHERE tv.vehicle = ? AND tv.day = ? ORDER BY tv.t_first""", (vk[0], day)).fetchall()
    trips, seen = [], set()
    t_first, t_last = covered_window(conn, origin)
    gaps = poll_gaps(conn, t_first, min(t_last + 60, int(time.time()))) if t_first else []
    for tkey, a, b, trip_id, route_id, head, block in rows:
        if trip_id in seen:
            continue
        seen.add(trip_id)
        r = ref.routes.get(route_id, {})
        st = conn.execute("SELECT MIN(departure_s), MAX(arrival_s) FROM stop_times WHERE trip_id = ?", (trip_id,)).fetchone()
        rk = conn.execute("SELECT key FROM route_keys WHERE route_id = ?", (route_id,)).fetchone()
        vis = []
        if rk:
            vis = sorted(tuple(x) for x in conn.execute(
                f"""SELECT seq, arr, delay FROM visits_all WHERE route = ? AND day = ? AND trip = ?
                    AND {observed()} AND delay IS NOT NULL""", (rk[0], day, tkey)))
        others = [ref.vehicle_by_key.get(x[0]) for x in conn.execute(
            "SELECT DISTINCT vehicle FROM trip_vehicle WHERE day = ? AND trip = ? AND vehicle != ?", (day, tkey, vk[0]))]
        s0, s1 = (st[0], st[1]) if st and st[0] is not None else (None, None)
        in_gap = s0 is not None and any(g0 - origin < s1 and g1 - origin > s0 for g0, g1 in gaps)
        trips.append({"trip_id": trip_id, "route_id": route_id, "short": r.get("route_short_name"),
                      "color": r.get("route_color"), "mode": r.get("mode"), "head": head, "block_id": block,
                      "sched_start": s0, "sched_end": s1,
                      "obs_start": vis[0][1] if vis else None, "obs_end": vis[-1][1] if vis else None,
                      "d_first": vis[0][2] if vis else None, "d_last": vis[-1][2] if vis else None,
                      "n": len(vis), "swapped_with": [o for o in others if o], "in_gap": in_gap})
    return {"vehicle_id": vehicle_id, "date": day_date(day).isoformat(), "origin": origin,
            "days": [day_date(d).isoformat() for d in days], "trips": trips,
            "blocks": sorted({t["block_id"] for t in trips if t["block_id"]}),
            "gaps": [[a - origin, b - origin] for a, b in gaps]}


# ---------------------------------------------------------------- data health

def health(ins: Insights, sc: Scope) -> dict:
    conn = ins.conn()
    ref = ins.ref()
    d0 = service_day_origin(day_date(sc.d0)) + 3 * 3600
    d1 = service_day_origin(day_date(sc.d1)) + 29 * 3600
    rows = conn.execute("SELECT ts, feed_ts, n_vehicles, n_stop_updates, error FROM polls WHERE ts >= ? AND ts < ? ORDER BY ts",
                        (d0, d1)).fetchall()
    ts = [r[0] for r in rows]
    lags = sorted(r[0] - r[1] for r in rows if r[1])
    errors = Counter(_error_kind(r[4]) for r in rows if r[4])
    gaps = poll_gaps(conn, ts[0], min(ts[-1] + 60, int(time.time()))) if ts else []
    # downsample to at most ~2000 points (per-minute medians when a range covers several days)
    step = max(1, len(rows) // 2000)
    series = {"ts": [], "veh": [], "su": [], "lag": [], "err": []}
    for k in range(0, len(rows), step):
        chunk = rows[k:k + step]
        series["ts"].append(chunk[0][0])
        series["veh"].append(statistics.median(r[2] or 0 for r in chunk) or None)
        series["su"].append(statistics.median(r[3] or 0 for r in chunk) or None)
        lg = [r[0] - r[1] for r in chunk if r[1]]
        series["lag"].append(statistics.median(lg) if lg else None)
        series["err"].append(sum(1 for r in chunk if r[4]))
    span = (ts[-1] - ts[0]) if ts else 0
    offline = sum(b - a for a, b in gaps)

    # coverage: scheduled stop visits outside gaps vs visits the collector wrote, per route
    sched_ex = Counter()
    first_stops = Counter()
    recorded = Counter()
    obs_n = Counter()
    for d in sc.days:
        f = ins.day(d)
        t_first, t_last = covered_window(conn, f.origin)
        if t_first is None:
            continue
        g = [(a - f.origin, b - f.origin) for a, b in poll_gaps(conn, t_first, min(t_last + 60, int(time.time())))]
        lo, hi = t_first - f.origin, t_last - f.origin
        for route_id, arr_s, first in conn.execute(
                """SELECT t.route_id, st.arrival_s,
                          st.stop_sequence = (SELECT MIN(stop_sequence) FROM stop_times x WHERE x.trip_id = st.trip_id)
                   FROM trips t JOIN service_dates sd ON sd.service_id = t.service_id AND sd.date = ?
                   JOIN stop_times st USING (trip_id) WHERE st.arrival_s BETWEEN ? AND ?""",
                (day_date(d).isoformat(), lo, hi)):
            if any(a <= arr_s <= b for a, b in g):
                continue
            sched_ex[route_id] += 1
            first_stops[route_id] += bool(first)
        for rk, n in f.recorded.items():
            recorded[ref.route_by_key.get(rk)] += n
        for rk, n in f.obs_count.items():
            obs_n[ref.route_by_key.get(rk)] += n
    coverage = []
    for rid, n in sched_ex.items():
        r = ref.routes.get(rid)
        if not r or n < 20:
            continue
        coverage.append({"route_id": rid, "short": r["route_short_name"], "color": r["route_color"], "mode": r["mode"],
                         "sched": n, "recorded": recorded.get(rid, 0), "observed": obs_n.get(rid, 0),
                         "first": first_stops.get(rid, 0), "share": recorded.get(rid, 0) / n})
    coverage.sort(key=lambda c: c["share"])
    tot_s = sum(sched_ex.values())
    tot_r = sum(v for k, v in recorded.items() if k)
    tot_o = sum(v for k, v in obs_n.items() if k)
    live = [d for d in ins.days_with_data()]
    by_dow = Counter(day_date(d["day"]).weekday() for d in live)
    return {
        "scope": sc.describe(),
        "kpi": {"last_poll": ts[-1] if ts else None, "polls": len(ts), "span_s": span, "offline_s": offline,
                "uptime": (1 - offline / span) if span else None,
                "lag_median": q(lags, .5), "lag_max": lags[-1] if lags else None,
                "errors": sum(errors.values()), "error_kinds": errors.most_common(5),
                "visits": tot_r, "observed": tot_o, "rejected": tot_r - tot_o},
        "series": series,
        "gaps": gaps,
        "coverage": coverage,
        "network_share": tot_r / tot_s if tot_s else None,
        "first_stops": sum(first_stops.values()),
        "maturity": {"days": len(live), "by_dow": [by_dow.get(i, 0) for i in range(7)],
                     "first": live[0]["date"] if live else None, "last": live[-1]["date"] if live else None},
    }


def _error_kind(e: str) -> str:
    if "HTTPSConnectionPool" in e or "Max retries" in e:
        return "HTTPS timeout"
    return e.split(":")[0][:60]


# ---------------------------------------------------------------- search

def search(ins: Insights, text: str, limit: int = 8) -> dict:
    conn = ins.conn()
    ref = ins.ref()
    t = text.strip()
    if not t:
        return {"routes": [], "stations": [], "trips": [], "vehicles": []}
    like = f"%{t}%"
    tl = t.lower()
    routes = [r for r in ref.routes.values()
              if tl == (r["route_short_name"] or "").lower() or tl in (r["route_long_name"] or "").lower()
              or (r["route_short_name"] or "").lower().startswith(tl)][:limit]
    stations = [dict(r) for r in conn.execute(
        "SELECT station_id, name, n_stops FROM stations WHERE name LIKE ? ORDER BY n_stops DESC, name LIMIT ?", (like, limit))]
    trips = [r[0] for r in conn.execute(
        "SELECT DISTINCT trip_id FROM trip_dim WHERE trip_id LIKE ? LIMIT ?", (t + "%", limit))]
    vehicles = [r[0] for r in conn.execute(
        "SELECT vehicle_id FROM vehicle_keys WHERE vehicle_id LIKE ? LIMIT ?", (t + "%", limit))]
    return {"routes": [{"route_id": r["route_id"], "short": r["route_short_name"], "long": r["route_long_name"],
                        "color": r["route_color"], "mode": r["mode"]} for r in routes],
            "stations": stations, "trips": trips, "vehicles": vehicles}


def hubs(ins: Insights, limit: int = 24) -> list[dict]:
    conn = ins.conn()
    return [dict(r) for r in conn.execute(
        """SELECT s.station_id, s.name, s.n_stops, COUNT(DISTINCT rs.route_id) AS n_routes FROM stations s
           JOIN route_stops rs USING (station_id) GROUP BY s.station_id ORDER BY n_routes DESC, s.n_stops DESC LIMIT ?""",
        (limit,))]


def vehicles_on_day(ins: Insights, sc: Scope) -> list[dict]:
    conn = ins.conn()
    ref = ins.ref()
    out = []
    for vk, n, routes, t0, t1 in conn.execute(
            """SELECT tv.vehicle, COUNT(DISTINCT tv.trip), GROUP_CONCAT(DISTINCT t.route_id), MIN(tv.t_first), MAX(tv.t_last)
               FROM trip_vehicle tv JOIN trip_dim t ON t.key = tv.trip WHERE tv.day = ?
               GROUP BY tv.vehicle ORDER BY COUNT(DISTINCT tv.trip) DESC""", (sc.d1,)):
        rids = (routes or "").split(",")
        out.append({"vehicle_id": ref.vehicle_by_key.get(vk), "trips": n, "t_first": t0, "t_last": t1,
                    "routes": [{"route_id": rid, "short": ref.routes[rid]["route_short_name"],
                                "color": ref.routes[rid]["route_color"], "mode": ref.routes[rid]["mode"]}
                               for rid in rids if rid in ref.routes]})
    return out


def vehicle_gps(ins: Insights, vehicle_id: str, service_date: str | None, max_points: int = 2000) -> dict | None:
    """A vehicle's GPS over its service day (first trip - 10 min .. last trip + 10 min), thinned to max_points.
    [service-day seconds, lat, lon, speed m/s, trip_id]"""
    v = vehicle_view(ins, vehicle_id, service_date)
    if v is None:
        return None
    conn = ins.conn()
    spans = [(t["obs_start"] if t["obs_start"] is not None else t["sched_start"],
              t["obs_end"] if t["obs_end"] is not None else t["sched_end"]) for t in v["trips"]]
    spans = [(a, b) for a, b in spans if a is not None and b is not None]
    if not spans:
        return {"vehicle_id": vehicle_id, "date": v["date"], "origin": v["origin"], "pings": []}
    t0 = v["origin"] + min(a for a, _ in spans) - 600
    t1 = v["origin"] + max(b for _, b in spans) + 600
    pts = vehicle_pings(conn, vehicle_id, t0, t1)
    step = max(1, len(pts) // max_points)
    # which trip each ping belongs to, from the vehicle's trip spans
    trips = [(v["origin"] + (t["obs_start"] if t["obs_start"] is not None else t["sched_start"] or 0),
              v["origin"] + (t["obs_end"] if t["obs_end"] is not None else t["sched_end"] or 0), t["trip_id"]) for t in v["trips"]]
    out = []
    for ts, lat, lon, speed, _b in pts[::step]:
        tid = next((tr for a, b, tr in trips if a - 120 <= ts <= b + 60), None)
        out.append([ts - v["origin"], lat, lon, speed, tid])
    return {"vehicle_id": vehicle_id, "date": v["date"], "origin": v["origin"], "pings": out}
