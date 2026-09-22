"""Poll UTA GTFS-realtime feeds and persist history.

TripUpdates carry predicted arrival/departure for the current and upcoming stops
of each active trip; a stop disappears once the vehicle has passed it. The collector
keeps every in-flight (trip, stop) prediction in memory (Tracker) and writes a visit
once it has left the feed, so the stored value is the prediction made as the bus was
at/leaving the stop -- i.e. the observed time -- and each visit is written once.

Writes are batched to keep disk wear low (see docs/adr/2026-09-21-2300-compact-history.md):
live vehicle state goes to a tmpfs database every poll; final visits, GPS pings and the
poll log are committed every COMMIT_EVERY_S; staged visits are merged into the clustered
visits table every MERGE_EVERY_S; in-flight state is saved every CHECKPOINT_EVERY_S and
on shutdown. A crash loses at most COMMIT_EVERY_S of GPS and poll log.
"""

import json
from compression import zstd
import logging
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache

import requests
from google.transit import gtfs_realtime_pb2 as rt

from . import db, gtfs_static, history
from .history import History, TripRun, Visit
from .timeutil import infer_service_date, service_day_origin

log = logging.getLogger(__name__)

VEHICLE_URL = "https://apps.rideuta.com/tms/gtfs/Vehicle"
TRIP_UPDATE_URL = "https://apps.rideuta.com/tms/gtfs/TripUpdate"
COMMIT_EVERY_S = 60
CHECKPOINT_EVERY_S = 300
MERGE_EVERY_S = 6 * 3600
SEAL_EVERY_S = 3600
# UTA regenerates both feeds about every 10 s (measured 2026-09-21); polling faster
# only re-reads the same snapshot, slower drops snapshots and stales observed times.
POLL_INTERVAL_S = 10.0
# GPS history keeps one ping per vehicle per this many seconds (vehicles report
# every ~10 s); the live map uses every snapshot regardless.
POSITION_EVERY_S = 30


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
    block_id: str | None
    shape_id: str | None
    service_id: str | None
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
        self.feed_version = db.get_meta(conn, "gtfs_feed_version")
        self.trip = lru_cache(maxsize=20000)(self._trip)
        self.route_short_name = lru_cache(maxsize=2000)(self._route_short_name)

    def _route_short_name(self, route_id: str) -> str | None:
        row = self.conn.execute(
            "SELECT route_short_name FROM routes WHERE route_id = ?", (route_id,)).fetchone()
        return row[0] if row else None

    def _trip(self, trip_id: str) -> TripInfo:
        row = self.conn.execute(
            "SELECT t.route_id, r.route_short_name, t.direction_id, t.trip_headsign, "
            "t.block_id, t.shape_id, t.service_id FROM trips t LEFT JOIN routes r USING (route_id) WHERE trip_id = ?",
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
            return TripInfo(None, None, None, None, None, None, None, stops)
        return TripInfo(*row, stops)

    def clear(self):
        self.feed_version = db.get_meta(self.conn, "gtfs_feed_version")
        self.trip.cache_clear()
        self.route_short_name.cache_clear()


def stop_event_rows(feed: rt.FeedMessage, lookup: StaticLookup):
    """One tuple per stop prediction: (service_date, trip_id, stop_sequence, stop_id, route_id,
    route_short_name, direction_id, headsign, vehicle_id, sched_arrival, sched_departure,
    obs_arrival, obs_departure, first_seen, last_seen, lead_s, trip), where trip is the
    trip_dim tuple (history.TRIP_COLS)."""
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
        trip = (lookup.feed_version, trip_id, route_id, route_short_name, info.direction_id, info.headsign,
                info.block_id, info.shape_id, info.service_id)
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
                arr, dep, seen, seen, arr - seen, trip,
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


def tu_vehicle_trips(tu_feed: rt.FeedMessage) -> dict[str, str]:
    """vehicle_id -> the trip TripUpdates says it is running."""
    return {
        ent.trip_update.vehicle.id: ent.trip_update.trip.trip_id
        for ent in tu_feed.entity
        if ent.HasField("trip_update") and ent.trip_update.vehicle.id
        and ent.trip_update.trip.schedule_relationship != rt.TripDescriptor.CANCELED
    }


def vehicle_state_rows(veh_feed: rt.FeedMessage, tu_feed: rt.FeedMessage,
                       events: list[tuple], lookup: StaticLookup, now: int):
    """Currently active vehicles: on a trip and reported within LIVE_MAX_AGE_S.

    The vehicle feed sometimes already names the vehicle's next trip in its block
    while TripUpdates is still predicting the current one, so the TripUpdate's
    trip wins when both mention the vehicle.
    """
    tu_trip = tu_vehicle_trips(tu_feed)
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


class Tracker:
    """In-flight visits and trip vehicles; hands them back once final (FINAL_AFTER_S out of the feed).

    Merging follows the v2 upsert: a newer sighting replaces the prediction and counts an update;
    the vehicle id is kept when a sighting lacks one. A trip's vehicle stretch closes when
    TripUpdates names a different vehicle or the trip leaves the feed.
    """

    def __init__(self):
        self.visits: dict[tuple, Visit] = {}      # (service_date, trip_id, seq)
        self.runs: dict[tuple, TripRun] = {}      # (service_date, trip_id)

    def update(self, events: list[tuple], feed_ts: int) -> tuple[list[Visit], list[TripRun]]:
        seen_visits, seen_trips = set(), {}
        for (sdate, trip_id, seq, stop_id, _r, _rs, _d, _h, vid, sa, sd, oa, od, fs, ls, _lead, trip) in events:
            k = (sdate, trip_id, seq)
            seen_visits.add(k)
            v = self.visits.get(k)
            if v is None:
                self.visits[k] = Visit(sdate, trip, seq, stop_id, vid, sa, sd, oa, od, fs, ls)
            elif ls > v.last_seen:
                v.vehicle_id = vid or v.vehicle_id
                v.obs_arrival, v.obs_departure, v.last_seen = oa, od, ls
                v.n_updates += 1
            cur = seen_trips.get((sdate, trip_id))
            if cur is None or seq < cur[1]:
                seen_trips[(sdate, trip_id)] = (vid, seq, ls, trip)
        closed = []
        for tk, (vid, seq, ls, trip) in seen_trips.items():
            r = self.runs.get(tk)
            if r is not None and vid and r.vehicle_id and vid != r.vehicle_id:
                closed.append(r)
                r = None
            if r is None:
                self.runs[tk] = TripRun(tk[0], trip, vid, ls, ls, seq, seq)
            elif ls >= r.t_last:
                r.t_last, r.seq_last = ls, seq
                r.vehicle_id = r.vehicle_id or vid
        cutoff = feed_ts - db.FINAL_AFTER_S
        final = [k for k, v in self.visits.items() if k not in seen_visits and v.last_seen < cutoff]
        ended = [k for k, r in self.runs.items() if k not in seen_trips and r.t_last < cutoff]
        return [self.visits.pop(k) for k in final], closed + [self.runs.pop(k) for k in ended]

    def save(self, conn: sqlite3.Connection) -> None:
        data = {"visits": [history.to_json(v) for v in self.visits.values()],
                "runs": [history.to_json(r) for r in self.runs.values()]}
        blob = zstd.compress(json.dumps(data, separators=(",", ":")).encode(), 3)
        conn.execute("INSERT OR REPLACE INTO collector_state VALUES ('tracker', ?)", (blob,))

    @classmethod
    def load(cls, conn: sqlite3.Connection) -> "Tracker":
        t = cls()
        row = conn.execute("SELECT data FROM collector_state WHERE name = 'tracker'").fetchone()
        if row:
            data = json.loads(zstd.decompress(row[0]))
            for v in map(history.visit_from_json, data["visits"]):
                t.visits[(v.service_date, v.trip[1], v.seq)] = v
            for r in map(history.run_from_json, data["runs"]):
                t.runs[(r.service_date, r.trip[1])] = r
            log.info("resumed %d in-flight visits, %d trips", len(t.visits), len(t.runs))
        return t


@dataclass
class PollState:
    """What the previous polls saw, carried between poll_once calls.

    Two out-of-sync servers answer the feed URLs, so a fetch can return an
    older snapshot than the last one; those are skipped.
    """
    tu_ts: int = 0
    veh_ts: int = 0
    events: list = field(default_factory=list)            # last processed stop-event rows
    position_ts: dict = field(default_factory=dict)       # vehicle_id -> last stored GPS ts
    tracker: Tracker = field(default_factory=Tracker)
    history: History | None = None                        # created on first write
    live: sqlite3.Connection | None = None                # live database, opened on first poll
    # written by commit(), every COMMIT_EVERY_S
    pending_visits: list = field(default_factory=list)
    pending_runs: list = field(default_factory=list)
    pending_gps: list = field(default_factory=list)
    pending_polls: list = field(default_factory=list)


def poll_once(conn: sqlite3.Connection, lookup: StaticLookup,
              store_positions: bool = True, state: PollState | None = None) -> dict:
    """Fetch both feeds and store any snapshot newer than the last one seen.
    Returns counts, or {"error": ...}."""
    state = state if state is not None else PollState()
    if state.history is None:
        state.history = History(conn)
    if state.live is None:
        state.live = db.connect_live(conn.execute("PRAGMA database_list").fetchone()[2] or None)
    started = int(time.time())
    try:
        tu_feed = fetch_feed(TRIP_UPDATE_URL)
        veh_feed = fetch_feed(VEHICLE_URL)
    except Exception as exc:  # network errors shouldn't kill the loop
        log.warning("poll failed: %s", exc)
        poll = (started, None, None, None, None, str(exc))
        state.pending_polls.append(poll)
        with state.live:
            state.live.execute("INSERT OR REPLACE INTO last_poll VALUES ('last',?,?,?,?,?,?)", poll)
        return {"error": str(exc)}

    tu_new = tu_feed.header.timestamp > state.tu_ts
    veh_new = veh_feed.header.timestamp > state.veh_ts
    events = list(stop_event_rows(tu_feed, lookup)) if tu_new else []
    final, runs = [], []
    if tu_new:
        state.tu_ts, state.events = tu_feed.header.timestamp, events
        final, runs = state.tracker.update(events, tu_feed.header.timestamp)
    vehicles, live, positions = [], [], []
    if veh_new:
        state.veh_ts = veh_feed.header.timestamp
        vehicles = list(vehicle_rows(veh_feed, lookup))
        live = list(vehicle_state_rows(veh_feed, tu_feed, state.events, lookup, int(time.time())))
        tu_trip = tu_vehicle_trips(tu_feed)
        for row in vehicles:
            vid, ts = row[0], row[1]
            if ts - state.position_ts.get(vid, 0) >= POSITION_EVERY_S:
                t = tu_trip.get(vid)
                positions.append((*row, t, lookup.trip(t).route_id if t else None))
                state.position_ts[vid] = ts
    poll = (started, tu_feed.header.timestamp, len(vehicles), len(tu_feed.entity), len(events), None)
    state.pending_visits += final
    state.pending_runs += runs
    state.pending_polls.append(poll)
    if store_positions:
        state.pending_gps += positions
    with state.live:
        if veh_new:
            state.live.execute("DELETE FROM vehicle_state")
            state.live.executemany("INSERT OR REPLACE INTO vehicle_state VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", live)
        for kind in ("last", "ok"):
            state.live.execute(f"INSERT OR REPLACE INTO last_poll VALUES ('{kind}',?,?,?,?,?,?)", poll)
    stats = {"vehicles": len(vehicles), "active": len(live), "positions": len(positions),
             "trip_updates": len(tu_feed.entity), "stop_updates": len(events),
             "visits_written": len(final), "in_flight": len(state.tracker.visits)}
    stale = [name for name, new in (("trip_updates", tu_new), ("vehicles", veh_new)) if not new]
    if stale:
        stats["repeated_snapshot"] = stale
    return stats


def commit(conn: sqlite3.Connection, state: PollState) -> int:
    """Write buffered final visits, trip vehicles, GPS pings and poll log in one transaction.
    Returns the number of visits written."""
    if state.history is None:
        state.history = History(conn)
    with conn:
        state.history.stage_visits(state.pending_visits)
        state.history.write_trip_runs(state.pending_runs)
        state.history.write_gps(state.pending_gps)
        conn.executemany("INSERT OR REPLACE INTO polls VALUES (?,?,?,?,?,?)", state.pending_polls)
    n = len(state.pending_visits)
    state.pending_visits, state.pending_runs, state.pending_gps, state.pending_polls = [], [], [], []
    return n


def checkpoint(conn: sqlite3.Connection, state: PollState) -> int:
    """Commit buffers and save in-flight state."""
    n = commit(conn, state)
    with conn:
        state.tracker.save(conn)
    return n


def merge(conn: sqlite3.Connection, state: PollState) -> int:
    """Merge staged visits into the visits table (and refresh day_stats)."""
    commit(conn, state)
    with conn:
        return state.history.merge_staged()


def run(db_path: str | None = None, interval: float = POLL_INTERVAL_S, static_check_hours: float = 6.0,
        store_positions: bool = True, stop_flag=None) -> None:
    conn = db.connect(db_path)
    db.init(conn)
    lookup = StaticLookup(conn)
    state = PollState(tracker=Tracker.load(conn), history=History(conn))
    last_static = 0.0
    last = dict.fromkeys(("merged", "checkpoint", "committed", "sealed"), time.time())
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
        stats = poll_once(conn, lookup, store_positions=store_positions, state=state)
        for name, every, job in (("merged", MERGE_EVERY_S, merge), ("checkpoint", CHECKPOINT_EVERY_S, checkpoint),
                                 ("committed", COMMIT_EVERY_S, commit)):
            if t0 - last[name] > every:
                stats[name] = job(conn, state)
                last[name] = last["committed"] = t0
                break               # each job starts with commit()
        if t0 - last["sealed"] > SEAL_EVERY_S:
            with conn:
                stats["gps_sealed"] = history.seal_gps(conn)
            last["sealed"] = t0
        log.info("poll: %s (%.1fs)", stats, time.time() - t0)
        wait = max(1.0, interval - (time.time() - t0))
        if stop_flag is not None:
            stop_flag.wait(wait)
        else:
            time.sleep(wait)
    checkpoint(conn, state)
    log.info("stopped; saved %d in-flight visits", len(state.tracker.visits))
