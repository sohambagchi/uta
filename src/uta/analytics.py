"""Query layer for route segments: trips on one route between two stations.

The dashboard filters and summarizes on the client (hour, weekday, outliers),
so these functions return per-trip samples in compact columnar form rather
than pre-aggregated statistics. Only the date range is applied here, since it
bounds how much data is sent.
"""

import math
import sqlite3
from collections import Counter, defaultdict
from datetime import date

from .db import EPOCH, observed
from .insights import NON_PASSENGER
from .timeutil import local

# Observed travel times outside this range are data errors, not trips.
MAX_TRAVEL_S = 4 * 3600


def _in(ids) -> str:
    return ",".join("?" * len(ids))


# ---------------------------------------------------------------- routes

def list_routes(conn: sqlite3.Connection) -> list[dict]:
    dirs = defaultdict(list)
    for r in conn.execute(
        """
        SELECT rs.route_id, rs.direction_id, COUNT(*) AS n_stations,
               (SELECT trip_headsign FROM trips t WHERE t.route_id = rs.route_id
                  AND COALESCE(t.direction_id, 0) = rs.direction_id
                GROUP BY trip_headsign ORDER BY COUNT(*) DESC LIMIT 1) AS headsign
        FROM route_stops rs GROUP BY rs.route_id, rs.direction_id
        """
    ):
        dirs[r["route_id"]].append(
            {"direction_id": r["direction_id"], "headsign": r["headsign"], "n_stations": r["n_stations"]})
    rows = conn.execute(
        "SELECT route_id, route_short_name, route_long_name, route_type, route_color, route_text_color "
        "FROM routes ORDER BY route_type, CAST(route_short_name AS INTEGER), route_short_name"
    ).fetchall()
    return [{**dict(r), "directions": sorted(dirs.get(r["route_id"], []), key=lambda d: d["direction_id"])}
            for r in rows]


def route_detail(conn: sqlite3.Connection, route_id: str) -> dict | None:
    route = conn.execute("SELECT * FROM routes WHERE route_id = ?", (route_id,)).fetchone()
    if route is None:
        return None
    directions = []
    for (direction_id,) in conn.execute(
            "SELECT DISTINCT direction_id FROM route_stops WHERE route_id = ? ORDER BY direction_id", (route_id,)):
        stations = [dict(r) for r in conn.execute(
            """
            SELECT rs.seq, rs.station_id, st.name, st.lat, st.lon, rs.stop_ids, rs.n_trips
            FROM route_stops rs JOIN stations st USING (station_id)
            WHERE rs.route_id = ? AND rs.direction_id = ? ORDER BY rs.seq
            """, (route_id, direction_id)) if not NON_PASSENGER.search(r["name"] or "")]
        for s in stations:
            s["stop_ids"] = s["stop_ids"].split()
        head = conn.execute(
            "SELECT trip_headsign, COUNT(*) AS n FROM trips WHERE route_id = ? AND COALESCE(direction_id, 0) = ? "
            "GROUP BY trip_headsign ORDER BY n DESC LIMIT 1", (route_id, direction_id)).fetchone()
        shape_id = conn.execute(
            "SELECT shape_id FROM trips WHERE route_id = ? AND COALESCE(direction_id, 0) = ? "
            "AND shape_id IS NOT NULL GROUP BY shape_id ORDER BY COUNT(*) DESC LIMIT 1",
            (route_id, direction_id)).fetchone()
        directions.append({
            "direction_id": direction_id,
            "headsign": head["trip_headsign"] if head else None,
            "max_trips": max((s["n_trips"] for s in stations), default=0),
            "stations": stations,
            "patterns": _patterns(conn, route_id, direction_id, stations),
            "shape": _shape(conn, shape_id[0]) if shape_id else [],
        })
    return {"route": dict(route), "directions": directions}


def _patterns(conn, route_id: str, direction_id: int, stations: list[dict]) -> list[dict]:
    """Distinct station sequences trips run, as indexes into `stations`, with trip counts.

    The merged station list can put stations from different trip patterns (a
    branch, a loop run as separate trips) in one line; the dashboard uses these
    to only offer destination stops some trip actually reaches.
    """
    index = {s["station_id"]: i for i, s in enumerate(stations)}
    counts: Counter = Counter()
    cur_trip, seq = None, []
    for trip_id, station_id in conn.execute(
        """
        SELECT st.trip_id, s.station_id FROM stop_times st
        JOIN trips t USING (trip_id) JOIN stops s USING (stop_id)
        WHERE t.route_id = ? AND COALESCE(t.direction_id, 0) = ?
        ORDER BY st.trip_id, st.stop_sequence
        """, (route_id, direction_id)):
        if trip_id != cur_trip:
            if seq:
                counts[tuple(seq)] += 1
            cur_trip, seq = trip_id, []
        i = index.get(station_id)
        if i is not None and (not seq or seq[-1] != i):
            seq.append(i)
    if seq:
        counts[tuple(seq)] += 1
    return [{"stations": list(p), "n_trips": n} for p, n in counts.most_common()]


def _shape(conn: sqlite3.Connection, shape_id: str) -> list[list[float]]:
    """Shape as [[lon, lat], ...] (GeoJSON order)."""
    return [[round(lon, 6), round(lat, 6)] for lat, lon in conn.execute(
        "SELECT lat, lon FROM shapes WHERE shape_id = ? ORDER BY seq", (shape_id,))]


def network(conn: sqlite3.Connection, tolerance_m: float = 15.0) -> list[dict]:
    """The most common shape of every route direction, simplified, for map context."""
    out = []
    for route_id, direction_id, shape_id, color in conn.execute(
        """
        SELECT t.route_id, COALESCE(t.direction_id, 0), t.shape_id, r.route_color
        FROM trips t JOIN routes r USING (route_id)
        WHERE t.shape_id IS NOT NULL
        GROUP BY t.route_id, COALESCE(t.direction_id, 0), t.shape_id
        HAVING COUNT(*) = (
            SELECT MAX(c) FROM (SELECT COUNT(*) AS c FROM trips t2
                                WHERE t2.route_id = t.route_id
                                  AND COALESCE(t2.direction_id, 0) = COALESCE(t.direction_id, 0)
                                GROUP BY t2.shape_id))
        """
    ):
        out.append({"route_id": route_id, "direction_id": direction_id, "color": color,
                    "coords": simplify(_shape(conn, shape_id), tolerance_m)})
    return out


def simplify(coords: list[list[float]], tolerance_m: float) -> list[list[float]]:
    """Douglas-Peucker on [lon, lat] points, tolerance in metres (equirectangular)."""
    if len(coords) < 3:
        return coords
    k = math.cos(math.radians(coords[0][1]))
    pts = [(x * 111_320 * k, y * 111_320) for x, y in coords]
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        (ax, ay), (bx, by) = pts[a], pts[b]
        dx, dy = bx - ax, by - ay
        norm = math.hypot(dx, dy) or 1e-9
        best, idx = 0.0, -1
        for i in range(a + 1, b):
            px, py = pts[i]
            d = abs(dy * (px - ax) - dx * (py - ay)) / norm
            if d > best:
                best, idx = d, i
        if best > tolerance_m:
            keep[idx] = True
            stack += [(a, idx), (idx, b)]
    return [c for c, k_ in zip(coords, keep) if k_]


# ---------------------------------------------------------------- segments

def _station(conn, station_id: str) -> dict | None:
    row = conn.execute("SELECT * FROM stations WHERE station_id = ?", (station_id,)).fetchone()
    return dict(row) if row else None


def _station_stops(conn, route_id: str, station_id: str) -> list[str]:
    """Stops of a station that the route uses (any direction)."""
    ids: set[str] = set()
    for (stop_ids,) in conn.execute(
            "SELECT stop_ids FROM route_stops WHERE route_id = ? AND station_id = ?", (route_id, station_id)):
        ids.update(stop_ids.split())
    return sorted(ids)


def _tightest(rows, key):
    """A loop trip may visit A or B twice; keep the shortest A->B span per trip."""
    best = {}
    for r in rows:
        k = key(r)
        if k not in best or r["b_seq"] - r["a_seq"] < best[k]["b_seq"] - best[k]["a_seq"]:
            best[k] = r
    return list(best.values())


def segment(conn: sqlite3.Connection, route_id: str, from_station: str, to_station: str,
            date_from: str | None = None, date_to: str | None = None) -> dict | None:
    """Everything the dashboard needs for one route between two stations."""
    a, b = _station(conn, from_station), _station(conn, to_station)
    if a is None or b is None:
        return None
    from_ids = _station_stops(conn, route_id, from_station)
    to_ids = _station_stops(conn, route_id, to_station)

    # directions in which the route reaches `from` before `to`
    seqs = defaultdict(dict)
    for direction_id, seq, station_id in conn.execute(
            "SELECT direction_id, seq, station_id FROM route_stops WHERE route_id = ? AND station_id IN (?, ?)",
            (route_id, from_station, to_station)):
        seqs[direction_id][station_id] = seq
    directions = [d for d, s in seqs.items()
                  if from_station in s and to_station in s and s[from_station] < s[to_station]]
    between = []
    if directions:
        d = directions[0]
        between = [dict(r) for r in conn.execute(
            """
            SELECT rs.seq, rs.station_id, st.name, st.lat, st.lon, rs.n_trips
            FROM route_stops rs JOIN stations st USING (station_id)
            WHERE rs.route_id = ? AND rs.direction_id = ? AND rs.seq BETWEEN ? AND ?
            ORDER BY rs.seq
            """, (route_id, d, seqs[d][from_station], seqs[d][to_station]))]

    result = {
        "route_id": route_id,
        "from": a, "to": b,
        "directions": directions,
        "stations": between,
        "geometry": [],
        "observed": _empty_observed(),
        "scheduled": {"minute": [], "dow": [], "dur": [], "weight": []},
    }
    if not from_ids or not to_ids:
        return result
    result["observed"] = observed_samples(conn, route_id, from_ids, to_ids, date_from, date_to)
    sched, shape_trip = scheduled_samples(conn, route_id, from_ids, to_ids)
    result["scheduled"] = sched
    if shape_trip:
        result["geometry"] = segment_geometry(conn, *shape_trip)
    return result


def _empty_observed() -> dict:
    return {k: [] for k in ("depart", "date", "dow", "minute", "dur", "sched_dur", "dep_delay",
                            "trip_id", "vehicle_id")}


def observed_samples(conn, route_id, from_ids, to_ids, date_from=None, date_to=None) -> dict:
    """Columnar observed trips A->B, oldest first. minute/dow are local departure time."""
    route = conn.execute("SELECT key FROM route_keys WHERE route_id = ?", (route_id,)).fetchone()
    stops = dict(conn.execute(
        f"SELECT stop_id, key FROM stop_keys WHERE stop_id IN ({_in(from_ids + to_ids)})", [*from_ids, *to_ids]))
    a_keys = [stops[s] for s in from_ids if s in stops]
    b_keys = [stops[s] for s in to_ids if s in stops]
    if route is None or not a_keys or not b_keys:
        return _empty_observed()
    days, day_params = "", []
    if date_from:
        days += " AND day >= ?"
        day_params.append((date.fromisoformat(date_from) - EPOCH).days)
    if date_to:
        days += " AND day <= ?"
        day_params.append((date.fromisoformat(date_to) - EPOCH).days)
    params: list = []

    # Each side is a range scan on the visits primary key (route, stop, day, ...), plus a
    # scan of the small staging table (visits_new: visits since the last merge, <= 6 h).
    def side(keys):
        where = f"route = ? AND stop IN ({_in(keys)}){days}"
        params.extend([route[0], *keys, *day_params] * 2)
        return f"SELECT * FROM visits WHERE {where} UNION ALL SELECT * FROM visits_new WHERE {where}"

    rows = conn.execute(
        f"""
        WITH a AS ({side(a_keys)}),
             b AS ({side(b_keys)})
        SELECT d.service_date, t.trip_id, vk.vehicle_id,
               a.seq AS a_seq, b.seq AS b_seq,
               d.origin + a.arr + COALESCE(a.dwell, 0) AS t0, d.origin + b.arr AS t1,
               d.origin + a.arr - a.delay + COALESCE(a.sched_dwell, 0) AS s0, d.origin + b.arr - b.delay AS s1
        FROM a
        JOIN b ON b.day = a.day AND b.trip = a.trip AND b.seq > a.seq
        JOIN days d ON d.day = a.day
        JOIN trip_dim t ON t.key = a.trip
        LEFT JOIN vehicle_keys vk ON vk.key = a.vehicle
        WHERE {observed("a")} AND {observed("b")}
        """,
        params,
    ).fetchall()
    out = _empty_observed()
    for r in sorted(_tightest(rows, lambda r: (r["service_date"], r["trip_id"])), key=lambda r: r["t0"]):
        if r["t0"] is None or r["t1"] is None:
            continue
        dur = r["t1"] - r["t0"]
        if not 0 < dur <= MAX_TRAVEL_S:
            continue
        dt = local(r["t0"])
        out["depart"].append(r["t0"])
        out["date"].append(r["service_date"])
        out["dow"].append(dt.weekday())
        out["minute"].append(dt.hour * 60 + dt.minute)
        out["dur"].append(dur)
        out["sched_dur"].append(r["s1"] - r["s0"] if r["s0"] is not None and r["s1"] is not None else None)
        out["dep_delay"].append(r["t0"] - r["s0"] if r["s0"] is not None else None)
        out["trip_id"].append(r["trip_id"])
        out["vehicle_id"].append(r["vehicle_id"])
    return out


def scheduled_samples(conn, route_id, from_ids, to_ids) -> tuple[dict, tuple | None]:
    """Timetabled trips A->B in the current feed, one row per (trip, weekday) it runs,
    weighted by the number of dates. Also returns (trip_id, a_seq, b_seq) of a trip
    on the most common shape, for drawing the segment."""
    rows = conn.execute(
        f"""
        SELECT a.trip_id, t.service_id, t.shape_id,
               a.stop_sequence AS a_seq, b.stop_sequence AS b_seq,
               a.departure_s AS t0, b.arrival_s AS t1
        FROM stop_times a
        JOIN stop_times b ON b.trip_id = a.trip_id AND b.stop_sequence > a.stop_sequence
        JOIN trips t ON t.trip_id = a.trip_id
        WHERE t.route_id = ? AND a.stop_id IN ({_in(from_ids)}) AND b.stop_id IN ({_in(to_ids)})
        """,
        [route_id, *from_ids, *to_ids],
    ).fetchall()
    pairs = [r for r in _tightest(rows, lambda r: r["trip_id"]) if r["t0"] is not None and r["t1"] is not None]
    service_ids = sorted({r["service_id"] for r in pairs})
    dow_counts: dict = defaultdict(dict)
    if service_ids:
        for sid, dow, n in conn.execute(
            f"SELECT service_id, dow, COUNT(*) FROM service_dates "
            f"WHERE service_id IN ({_in(service_ids)}) GROUP BY service_id, dow",
            service_ids,
        ):
            dow_counts[sid][dow] = n
    out = {"minute": [], "dow": [], "dur": [], "weight": []}
    for r in pairs:
        days_over = r["t0"] // 86400
        for dow, n in sorted(dow_counts.get(r["service_id"], {}).items()):
            out["minute"].append((r["t0"] // 60) % 1440)
            out["dow"].append((dow + days_over) % 7)
            out["dur"].append(r["t1"] - r["t0"])
            out["weight"].append(n)
    shape_trip = None
    shapes = Counter(r["shape_id"] for r in pairs if r["shape_id"])
    if shapes:
        top = shapes.most_common(1)[0][0]
        r = next(r for r in pairs if r["shape_id"] == top)
        shape_trip = (r["trip_id"], r["a_seq"], r["b_seq"])
    return out, shape_trip


def segment_geometry(conn, trip_id: str, a_seq: int, b_seq: int) -> list[list[float]]:
    """The part of the trip's shape between two of its stops, as [[lon, lat], ...]."""
    row = conn.execute("SELECT shape_id FROM trips WHERE trip_id = ?", (trip_id,)).fetchone()
    ends = conn.execute(
        "SELECT s.stop_lat, s.stop_lon FROM stop_times st JOIN stops s USING (stop_id) "
        "WHERE st.trip_id = ? AND st.stop_sequence IN (?, ?) ORDER BY st.stop_sequence",
        (trip_id, a_seq, b_seq)).fetchall()
    if row is None or row[0] is None or len(ends) != 2:
        return [[lon, lat] for lat, lon in ends]
    shape = _shape(conn, row[0])
    if not shape:
        return [[lon, lat] for lat, lon in ends]
    k = math.cos(math.radians(ends[0][0]))

    def nearest(lat, lon, start):
        best, idx = float("inf"), start
        for i in range(start, len(shape)):
            x, y = shape[i]
            d = ((x - lon) * k) ** 2 + (y - lat) ** 2
            if d < best:
                best, idx = d, i
        return idx

    i = nearest(ends[0][0], ends[0][1], 0)
    j = nearest(ends[1][0], ends[1][1], i)
    return [[ends[0][1], ends[0][0]], *shape[i:j + 1], [ends[1][1], ends[1][0]]]
