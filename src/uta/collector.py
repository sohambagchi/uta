"""Poll UTA GTFS-realtime feeds and persist history.

TripUpdates carry predicted arrival/departure for the current and upcoming stops
of each active trip; a stop disappears once the vehicle has passed it. We upsert
every (trip, stop) prediction on each poll, so the final stored value is the
prediction made as the bus was at/leaving the stop -- i.e. the observed time.
"""

import logging
import sqlite3
import time
from dataclasses import dataclass
from datetime import date, timedelta
from functools import lru_cache

import requests
from google.transit import gtfs_realtime_pb2 as rt

from . import db, gtfs_static
from .timeutil import infer_service_date, local, service_day_origin

log = logging.getLogger(__name__)

VEHICLE_URL = "https://apps.rideuta.com/tms/gtfs/Vehicle"
TRIP_UPDATE_URL = "https://apps.rideuta.com/tms/gtfs/TripUpdate"
PURGE_EVERY_S = 300


def fetch_feed(url: str) -> rt.FeedMessage:
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    msg = rt.FeedMessage()
    msg.ParseFromString(resp.content)
    return msg


@dataclass(frozen=True)
class TripInfo:
    route_id: str | None
    route_short_name: str | None
    direction_id: int | None
    headsign: str | None
    # stop_sequence -> (stop_id, arrival_s, departure_s)
    stops: dict


@dataclass(frozen=True)
class NextStop:
    """First upcoming stop of a trip in the current TripUpdates feed."""
    trip_id: str
    stop_id: str | None
    delay_s: int | None


class StaticLookup:
    """Cached trip/stop lookups against the static GTFS tables."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.trip = lru_cache(maxsize=20000)(self._trip)
        self.route_short_name = lru_cache(maxsize=2000)(self._route_short_name)

    def _route_short_name(self, route_id: str) -> str | None:
        row = self.conn.execute(
            "SELECT route_short_name FROM routes WHERE route_id = ?", (route_id,)).fetchone()
        return row[0] if row else None

    def _trip(self, trip_id: str) -> TripInfo:
        row = self.conn.execute(
            "SELECT t.route_id, r.route_short_name, t.direction_id, t.trip_headsign "
            "FROM trips t LEFT JOIN routes r USING (route_id) WHERE trip_id = ?",
            (trip_id,),
        ).fetchone()
        stops = {
            r[0]: (r[1], r[2], r[3])
            for r in self.conn.execute(
                "SELECT stop_sequence, stop_id, arrival_s, departure_s "
                "FROM stop_times WHERE trip_id = ?",
                (trip_id,),
            )
        }
        if row is None:
            return TripInfo(None, None, None, None, stops)
        return TripInfo(row[0], row[1], row[2], row[3], stops)

    def clear(self):
        self.trip.cache_clear()
        self.route_short_name.cache_clear()


UPSERT_EVENT = """
INSERT INTO stop_events (
    service_date, trip_id, stop_sequence, stop_id, route_id, route_short_name,
    direction_id, trip_headsign, vehicle_id, sched_arrival, sched_departure,
    obs_arrival, obs_departure, first_seen, last_seen, lead_s, n_updates
) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)
ON CONFLICT (service_date, trip_id, stop_sequence) DO UPDATE SET
    vehicle_id    = COALESCE(excluded.vehicle_id, vehicle_id),
    obs_arrival   = excluded.obs_arrival,
    obs_departure = excluded.obs_departure,
    last_seen     = excluded.last_seen,
    lead_s        = excluded.lead_s,
    n_updates     = n_updates + 1
WHERE excluded.last_seen > last_seen
"""


def stop_event_rows(feed: rt.FeedMessage, lookup: StaticLookup):
    feed_ts = feed.header.timestamp or int(time.time())
    for ent in feed.entity:
        if not ent.HasField("trip_update"):
            continue
        tu = ent.trip_update
        if tu.trip.schedule_relationship == rt.TripDescriptor.CANCELED:
            continue
        trip_id = tu.trip.trip_id
        info = lookup.trip(trip_id)
        route_id = info.route_id or tu.trip.route_id or None
        route_short_name = info.route_short_name or (lookup.route_short_name(route_id) if route_id else None)
        vehicle_id = tu.vehicle.id or None
        seen = tu.timestamp or feed_ts
        explicit_date = (
            date(int(tu.trip.start_date[:4]), int(tu.trip.start_date[4:6]), int(tu.trip.start_date[6:]))
            if tu.trip.start_date else None
        )
        for stu in tu.stop_time_update:
            if stu.schedule_relationship == rt.TripUpdate.StopTimeUpdate.SKIPPED:
                continue
            arr = stu.arrival.time if stu.HasField("arrival") and stu.arrival.time else None
            dep = stu.departure.time if stu.HasField("departure") and stu.departure.time else None
            if arr is None and dep is None:
                continue
            arr = arr or dep
            dep = dep or arr
            static = info.stops.get(stu.stop_sequence) if stu.stop_sequence else None
            if static is None and stu.stop_id:
                static = next((v for v in info.stops.values() if v[0] == stu.stop_id), None)
            stop_id = stu.stop_id or (static[0] if static else None)
            if stop_id is None:
                continue
            sched_arr_s = static[1] if static else None
            sched_dep_s = static[2] if static else None

            sdate = explicit_date or infer_service_date(arr, sched_arr_s)
            origin = service_day_origin(sdate)
            yield (
                sdate.isoformat(), trip_id, stu.stop_sequence, stop_id,
                route_id, route_short_name, info.direction_id, info.headsign,
                vehicle_id,
                origin + sched_arr_s if sched_arr_s is not None else None,
                origin + sched_dep_s if sched_dep_s is not None else None,
                arr, dep, seen, seen, arr - seen,
            )


def next_stops(events: list[tuple]) -> dict[str, NextStop]:
    """trip_id -> its first upcoming stop, from stop_event_rows output."""
    out: dict[str, tuple] = {}
    for e in events:
        trip_id, seq = e[1], e[2]
        if trip_id not in out or seq < out[trip_id][2]:
            out[trip_id] = e
    return {
        t: NextStop(t, e[3], e[11] - e[9] if e[9] is not None else None)
        for t, e in out.items()
    }


def vehicle_state_rows(veh_feed: rt.FeedMessage, tu_feed: rt.FeedMessage,
                       events: list[tuple], lookup: StaticLookup, now: int):
    """Currently active vehicles: on a trip and reported within LIVE_MAX_AGE_S.

    The vehicle feed sometimes already names the vehicle's next trip in its block
    while TripUpdates is still predicting the current one, so the TripUpdate's
    trip wins when both mention the vehicle.
    """
    tu_trip = {
        ent.trip_update.vehicle.id: ent.trip_update.trip.trip_id
        for ent in tu_feed.entity
        if ent.HasField("trip_update") and ent.trip_update.vehicle.id
        and ent.trip_update.trip.schedule_relationship != rt.TripDescriptor.CANCELED
    }
    nxt = next_stops(events)
    feed_ts = veh_feed.header.timestamp or now
    for ent in veh_feed.entity:
        if not ent.HasField("vehicle"):
            continue
        v = ent.vehicle
        vehicle_id = v.vehicle.id or ent.id
        ts = v.timestamp or feed_ts
        trip_id = tu_trip.get(vehicle_id) or v.trip.trip_id or None
        if trip_id is None or now - ts > db.LIVE_MAX_AGE_S:
            continue
        info = lookup.trip(trip_id)
        ns = nxt.get(trip_id)
        yield (
            vehicle_id, ts, trip_id, info.route_id or v.trip.route_id or None,
            info.direction_id, info.headsign,
            v.position.latitude, v.position.longitude,
            v.position.bearing if v.position.HasField("bearing") else None,
            v.position.speed if v.position.HasField("speed") else None,
            ns.delay_s if ns else None, ns.stop_id if ns else None,
        )


def vehicle_rows(feed: rt.FeedMessage, lookup: StaticLookup):
    feed_ts = feed.header.timestamp or int(time.time())
    for ent in feed.entity:
        if not ent.HasField("vehicle"):
            continue
        v = ent.vehicle
        trip_id = v.trip.trip_id or None
        route_id = v.trip.route_id or (lookup.trip(trip_id).route_id if trip_id else None)
        yield (
            v.vehicle.id or ent.id, v.timestamp or feed_ts, trip_id, route_id,
            v.position.latitude, v.position.longitude,
            v.position.bearing if v.position.HasField("bearing") else None,
            v.position.speed if v.position.HasField("speed") else None,
        )


def poll_once(conn: sqlite3.Connection, lookup: StaticLookup,
              store_positions: bool = True) -> dict:
    """Fetch both feeds and store them. Returns counts, or {"error": ...}."""
    started = int(time.time())
    try:
        tu_feed = fetch_feed(TRIP_UPDATE_URL)
        veh_feed = fetch_feed(VEHICLE_URL)
    except Exception as exc:  # network errors shouldn't kill the loop
        log.warning("poll failed: %s", exc)
        with conn:
            conn.execute("INSERT OR REPLACE INTO polls(ts, error) VALUES (?, ?)", (started, str(exc)))
        return {"error": str(exc)}

    events = list(stop_event_rows(tu_feed, lookup))
    vehicles = list(vehicle_rows(veh_feed, lookup))
    live = list(vehicle_state_rows(veh_feed, tu_feed, events, lookup, int(time.time())))
    with conn:
        conn.executemany(UPSERT_EVENT, events)
        conn.execute("DELETE FROM vehicle_state")
        conn.executemany("INSERT OR REPLACE INTO vehicle_state VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", live)
        if store_positions:
            conn.executemany(
                "INSERT OR IGNORE INTO vehicle_positions VALUES (?,?,?,?,?,?,?,?)", vehicles
            )
        conn.execute(
            "INSERT OR REPLACE INTO polls VALUES (?,?,?,?,?,NULL)",
            (started, tu_feed.header.timestamp, len(vehicles), len(tu_feed.entity), len(events)),
        )
    return {"vehicles": len(vehicles), "active": len(live), "trip_updates": len(tu_feed.entity),
            "stop_updates": len(events)}


def purge(conn: sqlite3.Connection) -> int:
    """Drop finalized stale visits from the last two service days."""
    since = (local(int(time.time())).date() - timedelta(days=2)).isoformat()
    with conn:
        return db.purge_stale_events(conn, since)


def run(db_path: str | None = None, interval: float = 30.0, static_check_hours: float = 6.0,
        store_positions: bool = True, stop_flag=None) -> None:
    conn = db.connect(db_path)
    db.init(conn)
    lookup = StaticLookup(conn)
    last_static = last_purge = 0.0
    while stop_flag is None or not stop_flag.is_set():
        t0 = time.time()
        if t0 - last_static > static_check_hours * 3600:
            try:
                if gtfs_static.refresh(conn):
                    lookup.clear()
                last_static = t0
            except Exception as exc:
                log.warning("static GTFS refresh failed: %s", exc)
                if last_static == 0.0 and db.get_meta(conn, "gtfs_feed_version") is None:
                    time.sleep(interval)
                    continue
        stats = poll_once(conn, lookup, store_positions=store_positions)
        if t0 - last_purge > PURGE_EVERY_S:
            stats["purged"] = purge(conn)
            last_purge = t0
        log.info("poll: %s (%.1fs)", stats, time.time() - t0)
        wait = max(1.0, interval - (time.time() - t0))
        if stop_flag is not None:
            stop_flag.wait(wait)
        else:
            time.sleep(wait)
