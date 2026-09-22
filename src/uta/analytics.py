"""Query layer: travel times between stops, route performance, stop search."""

import math
import sqlite3
from collections import defaultdict
from dataclasses import dataclass

from .db import observed
from .timeutil import local

DOW_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


# ---------------------------------------------------------------- statistics

def wstats(values: list[float], weights: list[float] | None = None) -> dict | None:
    """n, mean, and weighted percentiles. Weights default to 1."""
    if not values:
        return None
    if weights is None:
        weights = [1.0] * len(values)
    pairs = sorted(zip(values, weights))
    total = sum(w for _, w in pairs)
    mean = sum(v * w for v, w in pairs) / total

    def pct(p: float) -> float:
        target = p * total
        acc = 0.0
        for v, w in pairs:
            acc += w
            if acc >= target:
                return v
        return pairs[-1][0]

    var = sum(w * (v - mean) ** 2 for v, w in pairs) / total
    return {
        "n": len(values),
        "weight": round(total, 2),
        "mean": round(mean, 1),
        "std": round(math.sqrt(var), 1),
        "min": pairs[0][0],
        "p10": pct(0.10),
        "median": pct(0.50),
        "p90": pct(0.90),
        "max": pairs[-1][0],
    }


@dataclass
class Sample:
    route_id: str
    route: str          # short name
    headsign: str
    hour: int
    dow: int
    travel_s: float
    weight: float = 1.0
    sched_travel_s: float | None = None
    date: str | None = None
    trip_id: str | None = None
    depart_epoch: int | None = None


def group(samples: list[Sample], key) -> dict:
    buckets: dict = defaultdict(list)
    for s in samples:
        buckets[key(s)].append(s)
    return {
        k: wstats([s.travel_s for s in v], [s.weight for s in v])
        for k, v in buckets.items()
    }


def summarize(samples: list[Sample]) -> dict:
    by_route = group(samples, lambda s: s.route)
    by_hour = group(samples, lambda s: s.hour)
    by_dow = group(samples, lambda s: s.dow)
    by_route_hour = group(samples, lambda s: (s.route, s.hour))
    by_dow_hour = group(samples, lambda s: (s.dow, s.hour))
    by_route_dow = group(samples, lambda s: (s.route, s.dow))
    return {
        "overall": wstats([s.travel_s for s in samples], [s.weight for s in samples]),
        "by_route": [{"route": k, **v} for k, v in sorted(by_route.items(), key=lambda kv: kv[1]["mean"])],
        "by_hour": [{"hour": k, **v} for k, v in sorted(by_hour.items())],
        "by_dow": [{"dow": k, "dow_name": DOW_NAMES[k], **v} for k, v in sorted(by_dow.items())],
        "by_route_hour": [{"route": r, "hour": h, **v} for (r, h), v in sorted(by_route_hour.items())],
        "by_route_dow": [{"route": r, "dow": d, **v} for (r, d), v in sorted(by_route_dow.items())],
        "by_dow_hour": [{"dow": d, "hour": h, **v} for (d, h), v in sorted(by_dow_hour.items())],
    }


# ---------------------------------------------------------------- stops

def _in(ids: list[str]) -> str:
    return ",".join("?" * len(ids))


def expand_nearby(conn: sqlite3.Connection, stop_ids: list[str], radius_m: float) -> list[str]:
    """Add stops within radius_m of any given stop (e.g. other platforms / street sides)."""
    if radius_m <= 0 or not stop_ids:
        return stop_ids
    base = conn.execute(
        f"SELECT stop_lat, stop_lon FROM stops WHERE stop_id IN ({_in(stop_ids)})", stop_ids
    ).fetchall()
    out = set(stop_ids)
    dlat = radius_m / 111_320
    for lat, lon in base:
        dlon = radius_m / (111_320 * math.cos(math.radians(lat)))
        for sid, slat, slon in conn.execute(
            "SELECT stop_id, stop_lat, stop_lon FROM stops "
            "WHERE stop_lat BETWEEN ? AND ? AND stop_lon BETWEEN ? AND ?",
            (lat - dlat, lat + dlat, lon - dlon, lon + dlon),
        ):
            if haversine_m(lat, lon, slat, slon) <= radius_m:
                out.add(sid)
    return sorted(out)


def haversine_m(lat1, lon1, lat2, lon2) -> float:
    r = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def search_stops(conn: sqlite3.Connection, q: str, downstream_of: list[str] | None = None,
                 limit: int = 30) -> list[dict]:
    """Find stops by name / stop code. If downstream_of is given, only stops
    reachable on a single trip from one of those stops are returned."""
    q = q.strip()
    params: list = []
    where = []
    if q:
        terms = q.split()
        for t in terms:
            where.append("(s.stop_name LIKE ? OR s.stop_desc LIKE ? OR s.stop_code = ? OR s.stop_id = ?)")
            params += [f"%{t}%", f"%{t}%", t, t]
    join = ""
    if downstream_of:
        join = f"""JOIN (
            SELECT DISTINCT b.stop_id FROM stop_times a
            JOIN stop_times b ON b.trip_id = a.trip_id AND b.stop_sequence > a.stop_sequence
            WHERE a.stop_id IN ({_in(downstream_of)})
        ) d ON d.stop_id = s.stop_id"""
        params = list(downstream_of) + params
    sql = f"""
        SELECT s.stop_id, s.stop_code, s.stop_name, s.stop_desc, s.stop_lat, s.stop_lon,
               (SELECT group_concat(route_short_name, ', ') FROM (
                    SELECT DISTINCT r.route_short_name FROM stop_routes r
                    WHERE r.stop_id = s.stop_id ORDER BY r.route_short_name)) AS routes
        FROM stops s {join}
        {"WHERE " + " AND ".join(where) if where else ""}
        ORDER BY s.stop_name
        LIMIT ?
    """
    params.append(limit)
    return [dict(r) for r in conn.execute(sql, params)]


# ---------------------------------------------------------------- travel time

def _pick_pairs(rows, key):
    """For loop routes a trip may visit A or B twice; keep the tightest A->B pair per trip."""
    best = {}
    for r in rows:
        k = key(r)
        span = r["b_seq"] - r["a_seq"]
        if k not in best or span < best[k]["b_seq"] - best[k]["a_seq"]:
            best[k] = r
    return best.values()


def observed_samples(conn, from_ids, to_ids, routes=None, date_from=None, date_to=None) -> list[Sample]:
    params = list(from_ids) + list(to_ids)
    extra = ""
    if routes:
        extra += f" AND a.route_short_name IN ({_in(routes)})"
        params += routes
    if date_from:
        extra += " AND a.service_date >= ?"
        params.append(date_from)
    if date_to:
        extra += " AND a.service_date <= ?"
        params.append(date_to)
    rows = conn.execute(
        f"""
        SELECT a.service_date, a.trip_id, a.route_id, a.route_short_name, a.trip_headsign,
               a.stop_sequence AS a_seq, b.stop_sequence AS b_seq,
               COALESCE(a.obs_departure, a.obs_arrival) AS t0, b.obs_arrival AS t1,
               COALESCE(a.sched_departure, a.sched_arrival) AS s0, b.sched_arrival AS s1
        FROM stop_events a
        JOIN stop_events b
          ON b.service_date = a.service_date AND b.trip_id = a.trip_id
         AND b.stop_sequence > a.stop_sequence
        WHERE a.stop_id IN ({_in(from_ids)}) AND b.stop_id IN ({_in(to_ids)})
          AND {observed("a")} AND {observed("b")} {extra}
        """,
        params,
    ).fetchall()
    out = []
    for r in _pick_pairs(rows, lambda r: (r["service_date"], r["trip_id"])):
        travel = r["t1"] - r["t0"]
        if travel <= 0 or travel > 4 * 3600:
            continue
        dt = local(r["t0"])
        out.append(Sample(
            route_id=r["route_id"], route=r["route_short_name"] or r["route_id"] or "?",
            headsign=r["trip_headsign"] or "", hour=dt.hour, dow=dt.weekday(),
            travel_s=travel,
            sched_travel_s=(r["s1"] - r["s0"]) if r["s0"] and r["s1"] else None,
            date=r["service_date"], trip_id=r["trip_id"], depart_epoch=r["t0"],
        ))
    return out


def scheduled_samples(conn, from_ids, to_ids, routes=None) -> list[Sample]:
    """One sample per (trip, weekday), weighted by how many dates in the current
    feed that trip runs on that weekday."""
    params = list(from_ids) + list(to_ids)
    extra = ""
    if routes:
        extra = f" AND r.route_short_name IN ({_in(routes)})"
        params += routes
    rows = conn.execute(
        f"""
        SELECT a.trip_id, t.route_id, r.route_short_name, t.trip_headsign, t.service_id,
               a.stop_sequence AS a_seq, b.stop_sequence AS b_seq,
               a.departure_s AS t0, b.arrival_s AS t1
        FROM stop_times a
        JOIN stop_times b ON b.trip_id = a.trip_id AND b.stop_sequence > a.stop_sequence
        JOIN trips t ON t.trip_id = a.trip_id
        JOIN routes r ON r.route_id = t.route_id
        WHERE a.stop_id IN ({_in(from_ids)}) AND b.stop_id IN ({_in(to_ids)}) {extra}
        """,
        params,
    ).fetchall()
    pairs = list(_pick_pairs(rows, lambda r: r["trip_id"]))
    service_ids = sorted({r["service_id"] for r in pairs})
    dow_counts: dict = defaultdict(dict)
    if service_ids:
        for sid, dow, n in conn.execute(
            f"SELECT service_id, dow, COUNT(*) FROM service_dates "
            f"WHERE service_id IN ({_in(service_ids)}) GROUP BY service_id, dow",
            service_ids,
        ):
            dow_counts[sid][dow] = n
    out = []
    for r in pairs:
        if r["t0"] is None or r["t1"] is None:
            continue
        travel = r["t1"] - r["t0"]
        days_over = r["t0"] // 86400
        for dow, n in dow_counts.get(r["service_id"], {}).items():
            out.append(Sample(
                route_id=r["route_id"], route=r["route_short_name"] or r["route_id"],
                headsign=r["trip_headsign"] or "", hour=(r["t0"] // 3600) % 24,
                dow=(dow + days_over) % 7, travel_s=travel, weight=n, trip_id=r["trip_id"],
            ))
    return out


def _filter(samples: list[Sample], dows=None, hour_from=None, hour_to=None) -> list[Sample]:
    out = samples
    if dows:
        out = [s for s in out if s.dow in dows]
    if hour_from is not None:
        out = [s for s in out if s.hour >= hour_from]
    if hour_to is not None:
        out = [s for s in out if s.hour <= hour_to]
    return out


def travel_time(conn, from_ids, to_ids, *, radius_m=0.0, routes=None, dows=None,
                hour_from=None, hour_to=None, date_from=None, date_to=None) -> dict:
    from_ids = expand_nearby(conn, list(from_ids), radius_m)
    to_ids = expand_nearby(conn, list(to_ids), radius_m)

    obs = _filter(observed_samples(conn, from_ids, to_ids, routes, date_from, date_to),
                  dows, hour_from, hour_to)
    sch = _filter(scheduled_samples(conn, from_ids, to_ids, routes), dows, hour_from, hour_to)

    with_sched = [s for s in obs if s.sched_travel_s]
    adherence = wstats([s.travel_s - s.sched_travel_s for s in with_sched])

    recent = sorted(obs, key=lambda s: s.depart_epoch or 0, reverse=True)[:100]
    names = {r["stop_id"]: r["stop_name"] for r in conn.execute(
        f"SELECT stop_id, stop_name FROM stops WHERE stop_id IN ({_in(from_ids + to_ids)})",
        from_ids + to_ids)}
    return {
        "from": [{"stop_id": s, "stop_name": names.get(s)} for s in from_ids],
        "to": [{"stop_id": s, "stop_name": names.get(s)} for s in to_ids],
        "observed": summarize(obs),
        "scheduled": summarize(sch),
        "observed_minus_scheduled": adherence,
        "recent_trips": [
            {"date": s.date, "trip_id": s.trip_id, "route": s.route, "headsign": s.headsign,
             "depart": local(s.depart_epoch).strftime("%Y-%m-%d %H:%M"),
             "travel_s": s.travel_s, "sched_travel_s": s.sched_travel_s}
            for s in recent
        ],
    }


# ---------------------------------------------------------------- routes

def route_performance(conn, routes=None, date_from=None, date_to=None, route_type=None) -> dict:
    """Schedule adherence (observed - scheduled arrival) per route and hour."""
    where = [observed(), "sched_arrival IS NOT NULL"]
    params: list = []
    if route_type is not None:
        where.append("route_id IN (SELECT route_id FROM routes WHERE route_type = ?)")
        params.append(route_type)
    if routes:
        where.append(f"route_short_name IN ({_in(routes)})")
        params += routes
    if date_from:
        where.append("service_date >= ?")
        params.append(date_from)
    if date_to:
        where.append("service_date <= ?")
        params.append(date_to)
    w = " AND ".join(where)
    common = """
        COUNT(*) AS n,
        ROUND(AVG(obs_arrival - sched_arrival), 1) AS mean_delay_s,
        ROUND(100.0 * SUM(obs_arrival - sched_arrival BETWEEN -60 AND 300) / COUNT(*), 1) AS pct_on_time,
        ROUND(100.0 * SUM(obs_arrival - sched_arrival > 300) / COUNT(*), 1) AS pct_late,
        ROUND(100.0 * SUM(obs_arrival - sched_arrival < -60) / COUNT(*), 1) AS pct_early,
        COUNT(DISTINCT service_date || trip_id) AS trips
    """
    by_route = conn.execute(
        f"SELECT route_short_name AS route, {common} FROM stop_events WHERE {w} "
        f"GROUP BY route_short_name ORDER BY mean_delay_s DESC", params).fetchall()
    by_hour = conn.execute(
        f"SELECT CAST(strftime('%H', obs_arrival, 'unixepoch', 'localtime') AS INTEGER) AS hour, "
        f"{common} FROM stop_events WHERE {w} GROUP BY hour ORDER BY hour", params).fetchall()
    by_route_hour = conn.execute(
        f"SELECT route_short_name AS route, "
        f"CAST(strftime('%H', obs_arrival, 'unixepoch', 'localtime') AS INTEGER) AS hour, "
        f"{common} FROM stop_events WHERE {w} GROUP BY route, hour", params).fetchall()
    return {
        "by_route": [dict(r) for r in by_route],
        "by_hour": [dict(r) for r in by_hour],
        "by_route_hour": [dict(r) for r in by_route_hour],
    }
