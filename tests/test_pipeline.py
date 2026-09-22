"""End-to-end tests on a tiny synthetic GTFS feed + synthetic realtime updates."""

import io
import zipfile
from datetime import date

import pytest
from fastapi.testclient import TestClient
from google.transit import gtfs_realtime_pb2 as rt

from uta import analytics, collector, db, gps, gtfs_static, history
from uta.server import create_app
from uta.timeutil import infer_service_date, service_day_origin

# Two routes serve A -> B. Route 1 is scheduled at 10 min, route 2 at 20 min.
# Service "WK" runs Mon-Fri, "SA" Saturdays. Monday 2026-09-21 .. Sunday 2026-09-27.
FILES = {
    "feed_info.txt": "feed_publisher_name,feed_publisher_url,feed_lang,feed_version\nUTA,x,en,TEST1\n",
    "routes.txt": "route_id,route_short_name,route_long_name,route_type,route_color,route_text_color\n"
                  "R1,1,FAST,3,ff0000,ffffff\nR2,2,SLOW,3,00ff00,000000\n",
    "stops.txt": "stop_id,stop_code,stop_name,stop_desc,stop_lat,stop_lon,location_type,parent_station\n"
                 "A,100,Main St / 1st Ave,,40.7600,-111.8900,,\n"
                 "A2,101,Main St / 1st Ave (other side),,40.7601,-111.8901,,\n"
                 "M,102,Middle Stop,,40.7500,-111.8900,,\n"
                 "B,103,Center St / 9th Ave,,40.7400,-111.8900,,\n",
    "trips.txt": "route_id,service_id,trip_id,trip_headsign,direction_id,block_id,shape_id\n"
                 "R1,WK,T1,Downtown,0,,S1\nR1,WK,T2,Downtown,0,,S1\nR2,WK,T3,Downtown,0,,S1\nR1,SA,T4,Downtown,0,,S1\n",
    "stop_times.txt": "trip_id,arrival_time,departure_time,stop_id,stop_sequence,timepoint\n"
                      "T1, 8:00:00, 8:00:00,A,1,1\nT1, 8:05:00, 8:05:00,M,2,0\nT1, 8:10:00, 8:10:00,B,3,1\n"
                      "T2,17:00:00,17:00:00,A,1,1\nT2,17:10:00,17:10:00,B,2,1\n"
                      "T3, 8:30:00, 8:30:00,A,1,1\nT3, 8:50:00, 8:50:00,B,2,1\n"
                      "T4,25:00:00,25:00:00,A,1,1\nT4,25:10:00,25:10:00,B,2,1\n",
    "calendar.txt": "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n"
                    "WK,1,1,1,1,1,0,0,20260921,20260927\nSA,0,0,0,0,0,1,0,20260921,20260927\n",
    "calendar_dates.txt": "service_id,date,exception_type\nWK,20260925,2\n",
    "shapes.txt": "shape_id,shape_pt_lat,shape_pt_lon,shape_pt_sequence\nS1,40.76,-111.89,1\nS1,40.74,-111.89,2\n",
}


def make_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in FILES.items():
            zf.writestr(name, content)
    return buf.getvalue()


@pytest.fixture(autouse=True)
def live_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("UTA_LIVE_DIR", str(tmp_path))


@pytest.fixture
def conn(tmp_path):
    c = db.connect(str(tmp_path / "t.db"))
    db.init(c)
    assert gtfs_static.import_zip(c, make_zip())
    return c


def trip_update_feed(feed_ts, trips):
    """trips: {trip_id: [(stop_sequence, arrival_epoch, departure_epoch), ...]}"""
    msg = rt.FeedMessage()
    msg.header.gtfs_realtime_version = "2.0"
    msg.header.timestamp = feed_ts
    for trip_id, stus in trips.items():
        ent = msg.entity.add()
        ent.id = trip_id
        ent.trip_update.trip.trip_id = trip_id
        ent.trip_update.vehicle.id = "V" + trip_id
        for seq, arr, dep in stus:
            s = ent.trip_update.stop_time_update.add()
            s.stop_sequence = seq
            s.arrival.time = arr
            s.departure.time = dep
    return msg


class Feeder:
    """Runs TripUpdates feeds through the collector's tracker and writer, without the network."""

    def __init__(self, conn):
        self.conn = conn
        self.lookup = collector.StaticLookup(conn)
        self.tracker = collector.Tracker()
        self.history = history.History(conn)

    def __call__(self, feed):
        self._apply(list(collector.stop_event_rows(feed, self.lookup)), feed.header.timestamp)

    def flush(self, ts):
        """A later poll with nothing in the feed: everything tracked becomes final and is merged."""
        self._apply([], ts)
        with self.conn:
            self.history.merge_staged()

    def _apply(self, events, ts):
        final, runs = self.tracker.update(events, ts)
        with self.conn:
            self.history.stage_visits(final)
            self.history.write_trip_runs(runs)


MON = date(2026, 9, 21)
ORIGIN = service_day_origin(MON)


def at(h, m=0, s=0):
    return ORIGIN + h * 3600 + m * 60 + s


def test_import(conn):
    assert db.get_meta(conn, "gtfs_feed_version") == "TEST1"
    assert conn.execute("SELECT arrival_s FROM stop_times WHERE trip_id='T4' AND stop_sequence=1").fetchone()[0] == 25 * 3600
    # WK runs Mon-Thu (Friday removed by calendar_dates), SA on Saturday
    dates = conn.execute("SELECT dow FROM service_dates WHERE service_id='WK' ORDER BY date").fetchall()
    assert [r[0] for r in dates] == [0, 1, 2, 3]
    assert not gtfs_static.import_zip(conn, make_zip())  # same version -> skipped


def test_service_date_inference():
    # a trip scheduled at 25:00 on Monday's service day runs at 1am Tuesday
    assert infer_service_date(ORIGIN + 25 * 3600 + 600, 25 * 3600) == MON
    # 20 minutes late still maps to the same service day
    assert infer_service_date(at(8, 20), 8 * 3600) == MON


def test_observed_pipeline(conn):
    ingest = Feeder(conn)
    # poll 1: bus approaching A, predictions for A and B
    ingest( trip_update_feed(at(7, 58), {"T1": [(1, at(8, 1), at(8, 1, 30)), (3, at(8, 12), at(8, 12))]}))
    # poll 2: at A (departure updated), B prediction updated
    ingest( trip_update_feed(at(8, 1, 20), {"T1": [(1, at(8, 1), at(8, 1, 40)), (3, at(8, 13), at(8, 13))]}))
    # poll 3: A has left the feed (written: gone for > FINAL_AFTER_S); B imminent (still in flight)
    ingest(trip_update_feed(at(8, 13, 10), {"T1": [(3, at(8, 13, 20), at(8, 13, 30))]}))
    # staged, not merged yet, and already visible
    assert [r[0] for r in conn.execute("SELECT stop_sequence FROM stop_events")] == [1]
    assert conn.execute("SELECT COUNT(*) FROM visits").fetchone()[0] == 0
    assert analytics.segment(conn, "R1", "A", "M")["observed"]["dur"] == []
    ingest.flush(at(9))

    rows = {r["stop_sequence"]: r for r in conn.execute("SELECT * FROM stop_events")}
    assert rows[1]["obs_departure"] == at(8, 1, 40)
    assert rows[1]["n_updates"] == 2
    assert rows[1]["stop_id"] == "A" and rows[1]["route_short_name"] == "1"
    assert rows[1]["sched_arrival"] == at(8)
    assert rows[3]["obs_arrival"] == at(8, 13, 20)
    assert rows[3]["lead_s"] == 10

    seg = analytics.segment(conn, "R1", "A", "B")
    obs = seg["observed"]
    assert obs["dur"] == [at(8, 13, 20) - at(8, 1, 40)]  # 700 s
    assert obs["sched_dur"] == [600]
    assert obs["dep_delay"] == [100]
    assert obs["minute"] == [8 * 60 + 1] and obs["dow"] == [0] and obs["date"] == ["2026-09-21"]


def test_stale_predictions_are_kept_but_not_observed(conn):
    # only ever saw a far-future prediction for B (e.g. trip dropped from feed)
    ingest = Feeder(conn)
    ingest(trip_update_feed(at(7, 0), {"T1": [(1, at(8, 0), at(8, 0)), (3, at(8, 10), at(8, 10))]}))
    ingest.flush(at(9))
    assert analytics.segment(conn, "R1", "A", "B")["observed"]["dur"] == []
    assert conn.execute("SELECT COUNT(*) FROM stop_events").fetchone()[0] == 2
    assert tuple(conn.execute("SELECT n_visits, n_observed, n_trips FROM day_stats").fetchone()) == (2, 0, 0)


def test_segment_scheduled_and_shape(conn):
    seg = analytics.segment(conn, "R1", "A", "B")
    sch = seg["scheduled"]
    rows = sorted(zip(sch["minute"], sch["dow"], sch["dur"], sch["weight"]))
    # T1 (8:00) and T2 (17:00) Mon-Thu; T4 Saturday 25:00 -> Sunday 1am
    assert (60, 6, 600, 1) in rows
    assert [r for r in rows if r[0] == 480] == [(480, d, 600, 1) for d in range(4)]
    assert all(r[1] != 4 for r in rows)  # Friday removed by calendar_dates
    assert seg["directions"] == [0]
    assert [s["station_id"] for s in seg["stations"]] == ["A", "M", "B"]
    assert seg["geometry"][0] == [-111.89, 40.76] and seg["geometry"][-1] == [-111.89, 40.74]
    # route 2 never stops at M
    assert analytics.segment(conn, "R2", "A", "M")["scheduled"]["dur"] == []
    # reversed: no direction reaches B before A
    assert analytics.segment(conn, "R1", "B", "A")["directions"] == []


def test_routes_and_detail(conn):
    routes = {r["route_id"]: r for r in analytics.list_routes(conn)}
    assert routes["R1"]["directions"] == [{"direction_id": 0, "headsign": "Downtown", "n_stations": 3}]
    d = analytics.route_detail(conn, "R1")["directions"][0]
    assert [s["station_id"] for s in d["stations"]] == ["A", "M", "B"]
    assert d["stations"][0]["stop_ids"] == ["A"]
    assert d["max_trips"] == 3 and len(d["shape"]) == 2
    # T1 runs A-M-B; T2 and T4 run A-B
    assert d["patterns"] == [{"stations": [0, 2], "n_trips": 2}, {"stations": [0, 1, 2], "n_trips": 1}]


def test_simplify():
    line = [[0, 0], [0.00001, 0.0005], [0, 0.001]]   # ~1 m off a straight line
    assert analytics.simplify(line, 5) == [[0, 0], [0, 0.001]]
    assert len(analytics.simplify(line, 0.1)) == 3


def test_api(conn, tmp_path):
    client = TestClient(create_app(str(tmp_path / "t.db")))
    assert client.get("/api/status").json()["gtfs_feed_version"] == "TEST1"
    assert len(client.get("/api/routes").json()) == 2
    assert client.get("/api/routes/R1").status_code == 200
    assert client.get("/api/routes/nope").status_code == 404
    seg = client.get("/api/segment", params={"route_id": "R1", "from": "A", "to": "B"}).json()
    assert len(seg["scheduled"]["dur"]) > 0
    assert client.get("/api/segment", params={"route_id": "R1", "from": "X", "to": "B"}).status_code == 404
    assert len(client.get("/api/network").json()) == 2
    assert client.get("/api/vehicles/live").json() == {"as_of": None, "vehicles": []}
    assert client.get("/").status_code == 200


# ---------------------------------------------------------------- data foundations

def test_stations_group_bays_and_street_sides(conn):
    assert gtfs_static.normalize_stop_name("1940. W North Temple Station (EB)") == "1940 w n temple station"
    assert gtfs_static.normalize_stop_name("Riverdale Rd / 4050 S (NB) (Riverda") == "riverdale rd 4050 s"
    station = dict(conn.execute("SELECT stop_id, station_id FROM stops"))
    assert station["A"] == station["A2"] == "A"
    assert station["M"] == "M" and station["B"] == "B"
    assert tuple(conn.execute("SELECT name, n_stops FROM stations WHERE station_id = 'A'").fetchone()) == ("Main St / 1st Ave", 2)


def test_route_stops_merge_patterns(conn):
    rows = conn.execute(
        "SELECT station_id, n_trips FROM route_stops WHERE route_id = 'R1' AND direction_id = 0 ORDER BY seq"
    ).fetchall()
    # T2/T4 run A->B, T1 also stops at M in between
    assert [tuple(r) for r in rows] == [("A", 3), ("M", 1), ("B", 3)]


def test_observed_window_keeps_all_visits(conn):
    # A left the feed 60 s before its predicted arrival: an early-dropped prediction
    ingest = Feeder(conn)
    ingest(trip_update_feed(at(7, 59), {"T1": [(1, at(8, 0), at(8, 0)), (3, at(8, 10), at(8, 10))]}))
    ingest(trip_update_feed(at(8, 9, 50), {"T1": [(3, at(8, 10), at(8, 10))]}))
    ingest.flush(at(9))
    lead = dict(conn.execute("SELECT stop_sequence, lead_s FROM stop_events"))
    assert lead == {1: 60, 3: 10}
    assert conn.execute("SELECT COUNT(*) FROM observed_stop_events").fetchone()[0] == 1
    assert tuple(conn.execute("SELECT n_visits, n_observed, n_trips FROM day_stats").fetchone()) == (2, 1, 1)


def test_visit_that_returns_to_the_feed_is_merged(conn):
    ingest = Feeder(conn)
    ingest(trip_update_feed(at(7, 50), {"T1": [(3, at(8, 10), at(8, 10))]}))
    ingest.flush(at(8))                     # dropped out: written once
    ingest(trip_update_feed(at(8, 9, 55), {"T1": [(3, at(8, 10, 5), at(8, 10, 5))]}))
    ingest.flush(at(9))
    [r] = conn.execute("SELECT * FROM stop_events").fetchall()
    assert (r["obs_arrival"], r["first_seen"], r["last_seen"], r["n_updates"]) == (
        at(8, 10, 5), at(7, 50), at(8, 9, 55), 2)
    assert tuple(conn.execute("SELECT n_visits, n_observed FROM day_stats").fetchone()) == (1, 1)


def test_trip_vehicle_records_a_swap(conn):
    ingest = Feeder(conn)
    feed = trip_update_feed(at(7, 55), {"T1": [(1, at(8), at(8)), (2, at(8, 5), at(8, 5)), (3, at(8, 10), at(8, 10))]})
    ingest(feed)
    feed = trip_update_feed(at(8, 3), {"T1": [(2, at(8, 5), at(8, 5)), (3, at(8, 10), at(8, 10))]})
    feed.entity[0].trip_update.vehicle.id = "SPARE"
    ingest(feed)
    ingest.flush(at(9))
    rows = conn.execute(
        "SELECT vk.vehicle_id, tv.t_first, tv.t_last, tv.seq_first, tv.seq_last, t.block_id FROM trip_vehicle tv "
        "JOIN vehicle_keys vk ON vk.key = tv.vehicle JOIN trip_dim t ON t.key = tv.trip ORDER BY t_first").fetchall()
    assert [tuple(r) for r in rows] == [("VT1", at(7, 55), at(7, 55), 1, 1, ""), ("SPARE", at(8, 3), at(8, 3), 2, 2, "")]


def test_tracker_state_survives_restart(conn):
    ingest = Feeder(conn)
    ingest(trip_update_feed(at(7, 58), {"T1": [(1, at(8, 1), at(8, 1, 30)), (3, at(8, 12), at(8, 12))]}))
    with conn:
        ingest.tracker.save(conn)
    resumed = collector.Tracker.load(conn)
    assert resumed.visits == ingest.tracker.visits and resumed.runs == ingest.tracker.runs
    ingest.tracker = resumed
    ingest(trip_update_feed(at(8, 1, 20), {"T1": [(3, at(8, 13), at(8, 13))]}))
    ingest.flush(at(9))
    assert conn.execute("SELECT SUM(n_updates) FROM stop_events").fetchone()[0] == 3


def test_events_without_stop_are_dropped(conn):
    feed = trip_update_feed(at(8), {"T1": [(9, at(8, 1), at(8, 1))]})   # no such stop_sequence
    assert list(collector.stop_event_rows(feed, collector.StaticLookup(conn))) == []


def vehicle_feed(feed_ts, vehicles):
    """vehicles: [(vehicle_id, trip_id, ts, lat, lon)]"""
    msg = rt.FeedMessage()
    msg.header.gtfs_realtime_version = "2.0"
    msg.header.timestamp = feed_ts
    for vid, trip_id, ts, lat, lon in vehicles:
        ent = msg.entity.add()
        ent.id = vid
        ent.vehicle.vehicle.id = vid
        if trip_id:
            ent.vehicle.trip.trip_id = trip_id
        ent.vehicle.timestamp = ts
        ent.vehicle.position.latitude = lat
        ent.vehicle.position.longitude = lon
    return msg


def test_vehicle_state_only_active(conn):
    now = at(8, 2)
    tu = trip_update_feed(now, {"T1": [(3, at(8, 12), at(8, 12))]})   # 2 min late at B
    lookup = collector.StaticLookup(conn)
    events = list(collector.stop_event_rows(tu, lookup))
    veh = vehicle_feed(now, [
        ("VT1", "T2", now - 5, 40.75, -111.89),   # names its next trip; TripUpdates says T1
        ("IDLE", None, now - 5, 40.7, -111.9),    # not on a trip
        ("GONE", "T3", now - 900, 40.7, -111.9),  # stale report
    ])
    rows = list(collector.vehicle_state_rows(veh, tu, events, lookup, now))
    assert len(rows) == 1
    vid, _, trip_id, route_id, *_, delay_s, next_stop = rows[0]
    assert (vid, trip_id, route_id, delay_s, next_stop) == ("VT1", "T1", "R1", 120, "B")


def test_migration_from_v1(tmp_path):
    path = str(tmp_path / "old.db")
    c = db.connect(path)
    db.init(c)
    gtfs_static.import_zip(c, make_zip())
    # simulate a v1 database: no station column/tables filled, old version marker
    c.execute("UPDATE stops SET station_id = NULL")
    c.execute("DELETE FROM route_stops")
    db.set_meta(c, "schema_version", "1")
    c.commit()
    db.init(c)
    assert c.execute("SELECT COUNT(*) FROM stops WHERE station_id IS NULL").fetchone()[0] == 0
    assert c.execute("SELECT COUNT(*) FROM route_stops").fetchone()[0] > 0
    assert db.get_meta(c, "schema_version") == str(db.SCHEMA_VERSION)


def test_poll_skips_repeated_snapshots_and_samples_gps(conn, monkeypatch):
    feeds = {}
    monkeypatch.setattr(collector, "fetch_feed", lambda url: feeds[url])
    monkeypatch.setattr(collector.time, "time", lambda: at(8, 2))
    lookup, state = collector.StaticLookup(conn), collector.PollState()

    def serve(ts, vehicle_ts):
        feeds[collector.TRIP_UPDATE_URL] = trip_update_feed(ts, {"T1": [(3, at(8, 12), at(8, 12))]})
        feeds[collector.VEHICLE_URL] = vehicle_feed(ts, [("VT1", "T1", vehicle_ts, 40.75, -111.89)])
        return collector.poll_once(conn, lookup, state=state)

    first = serve(at(8, 1), at(8, 1))
    assert first["stop_updates"] == 1 and first["positions"] == 1 and "repeated_snapshot" not in first
    # the other backend still serves the previous snapshot: nothing is written
    stale = serve(at(8, 0, 58), at(8, 0, 58))
    assert stale["repeated_snapshot"] == ["trip_updates", "vehicles"] and stale["stop_updates"] == 0
    assert state.live.execute("SELECT COUNT(*) FROM vehicle_state").fetchone()[0] == 1
    # 10 s later: live state updates, GPS history waits for POSITION_EVERY_S
    nxt = serve(at(8, 1, 10), at(8, 1, 10))
    assert nxt["active"] == 1 and nxt["positions"] == 0
    assert serve(at(8, 1, 31), at(8, 1, 31))["positions"] == 1
    assert list(gps.read(conn)) == []         # buffered until the next commit
    collector.commit(conn, state)
    assert conn.execute("SELECT COUNT(*) FROM polls").fetchone()[0] == 1   # keyed by the (frozen) wall clock
    pings = list(gps.read(conn))
    assert [(p[0], p[1], p[2], p[3], p[8]) for p in pings] == [
        ("VT1", at(8, 1), "T1", "R1", "T1"), ("VT1", at(8, 1, 31), "T1", "R1", "T1")]
    # sealing moves closed days into blocks without changing what is read back
    with conn:
        assert history.seal_gps(conn, now=at(8, 1) + 86400) == 2
    assert list(gps.read(conn)) == pings
    assert conn.execute("SELECT COUNT(*) FROM gps_recent").fetchone()[0] == 0


# ---------------------------------------------------------------- schema guard

def test_newer_database_is_refused(tmp_path):
    c = db.connect(str(tmp_path / "t.db"))
    db.init(c)
    db.set_meta(c, "schema_version", str(db.SCHEMA_VERSION + 1))
    c.commit()
    with pytest.raises(db.SchemaMismatch):
        db.init(c)


def test_server_wont_migrate_but_collector_backs_up_first(tmp_path):
    path = tmp_path / "t.db"
    c = db.connect(str(path))
    db.init(c)
    gtfs_static.import_zip(c, make_zip())
    db.set_meta(c, "schema_version", "1")
    c.commit()
    with pytest.raises(db.SchemaMismatch):
        create_app(str(path))
    assert db.get_meta(c, "schema_version") == "1"
    assert not list(tmp_path.glob("*.bak*"))

    db.init(c)  # the collector's path
    assert db.get_meta(c, "schema_version") == str(db.SCHEMA_VERSION)
    [bak] = tmp_path.glob("t.db.pre-v*.bak.zst")
    db.restore_backup(str(bak), str(tmp_path / "restored.db"))
    old = db.connect(str(tmp_path / "restored.db"), readonly=True)
    assert db.get_meta(old, "schema_version") == "1"
    assert old.execute("SELECT COUNT(*) FROM stops").fetchone()[0] == 4


def test_snapshot_cli(conn, tmp_path):
    from uta.__main__ import main
    src, dest = tmp_path / "t.db", tmp_path / "snap" / "dev.db"
    main(["--db", str(src), "snapshot", str(dest)])
    snap = db.connect(str(dest), readonly=True)
    assert snap.execute("SELECT COUNT(*) FROM stops").fetchone()[0] == 4
    with pytest.raises(SystemExit):
        main(["--db", str(src), "snapshot", str(src)])


def test_old_backups_are_pruned(tmp_path):
    import os
    for i in range(5):
        f = tmp_path / f"t.db.pre-v{i}-x.bak{'.zst' if i % 2 else ''}"
        f.write_bytes(b"x")
        os.utime(f, (i, i))
    db.prune_backups(str(tmp_path / "t.db"), keep=2)
    assert sorted(f.name for f in tmp_path.iterdir()) == ["t.db.pre-v3-x.bak.zst", "t.db.pre-v4-x.bak"]


# ---------------------------------------------------------------- compact history

def test_gps_codec_is_lossless():
    import random
    import struct
    f32 = lambda x: struct.unpack("<f", struct.pack("<f", x))[0]
    rnd = random.Random(1)
    rows = [(1790000000 + 30 * i, rnd.choice([None, 1, 2]), rnd.choice([None, 3]),
             f32(40.5 + rnd.random()), f32(-111.9 + rnd.random() / 10),
             rnd.choice([None, f32(rnd.random() * 360), round(rnd.random() * 360, 2)]),
             rnd.choice([0.0, f32(rnd.random() * 20), -1.5, None]))
            for i in range(500)]
    rows = [(*r[:5], f32(r[5]) if r[5] is not None else None, r[6]) for r in rows]
    assert gps.decode(gps.encode(rows)) == rows
    assert gps.decode(gps.encode(rows[:1])) == rows[:1]


# v2 tables, as the collector wrote them before schema v3
V2_TABLES = """
DROP VIEW IF EXISTS observed_stop_events;
DROP VIEW IF EXISTS stop_events;
CREATE TABLE stop_events (
    service_date TEXT, trip_id TEXT, stop_sequence INTEGER, stop_id TEXT, route_id TEXT,
    route_short_name TEXT, direction_id INTEGER, trip_headsign TEXT, vehicle_id TEXT,
    sched_arrival INTEGER, sched_departure INTEGER, obs_arrival INTEGER, obs_departure INTEGER,
    first_seen INTEGER, last_seen INTEGER, lead_s INTEGER, n_updates INTEGER DEFAULT 1,
    PRIMARY KEY (service_date, trip_id, stop_sequence)) WITHOUT ROWID;
CREATE TABLE vehicle_positions (
    vehicle_id TEXT, ts INTEGER, trip_id TEXT, route_id TEXT, lat REAL, lon REAL, bearing REAL, speed REAL,
    PRIMARY KEY (vehicle_id, ts)) WITHOUT ROWID;
"""


def test_migration_from_v2_is_lossless(tmp_path):
    path = tmp_path / "v2.db"
    c = db.connect(str(path))
    db.init(c)
    gtfs_static.import_zip(c, make_zip())
    c.executescript(V2_TABLES)
    events = [
        ("2026-09-21", "T1", 1, "A", "R1", "1", 0, "Downtown", "07001", at(8), at(8), at(8, 1), at(8, 1, 40),
         at(7, 58), at(8, 1, 20), at(8, 1) - at(8, 1, 20), 2),
        ("2026-09-21", "T1", 3, "B", "R1", "1", 0, "Downtown", None, at(8, 10), at(8, 10, 30), at(8, 13), at(8, 13),
         at(7, 58), at(8, 12), 60, 5),                                  # outside the observed window
        ("2026-09-21", "GONE", 4, None, None, None, None, None, "L9", None, None, at(9), at(9),
         at(8, 59), at(9), 0, 1),                                       # trip and stop unknown to the GTFS
        ("2026-09-22", "T4", 1, "A", "R1", "1", 0, "Downtown", "L9", at(49), at(49), at(49, 2), at(49, 2),
         at(49, 1), at(49, 2), 0, 1),
    ]
    c.executemany("INSERT INTO stop_events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", events)
    pings = [("07001", at(8, i), "T1", "R1", 40.75 + i / 1e3, -111.89, 310.45 if i % 2 else None, 12.0477276)
             for i in range(4)] + [("L9", at(33), None, None, 40.1, -111.8, 0.0, 0.0)]
    c.executemany("INSERT INTO vehicle_positions VALUES (?,?,?,?,?,?,?,?)", pings)
    original_pings = set(map(tuple, c.execute("SELECT * FROM vehicle_positions")))
    db.set_meta(c, "schema_version", "2")
    c.commit()

    db.init(c)
    assert db.get_meta(c, "schema_version") == "3"
    assert list(tmp_path.glob("v2.db.pre-v3-*.bak.zst"))
    got = [tuple(r) for r in c.execute("SELECT * FROM stop_events ORDER BY service_date, trip_id, stop_sequence")]
    assert got == sorted(events, key=lambda e: (e[0], e[1], e[2]))
    assert {p[:8] for p in gps.read(c)} == original_pings
    assert tuple(c.execute("SELECT (SELECT SUM(n) FROM gps_blocks) IS NULL, COUNT(*) FROM gps_recent").fetchone()) == (1, 5)  # not closed yet
    assert tuple(c.execute("SELECT block_id, service_id FROM trip_dim WHERE trip_id = 'T1'").fetchone()) == ("", "WK")
    assert not c.execute("SELECT 1 FROM sqlite_master WHERE name IN ('vehicle_positions') ").fetchone()
    status = TestClient(create_app(str(path))).get("/api/status").json()["observed"]
    assert status == {"first": "2026-09-21", "last": "2026-09-22", "n": 3, "trips": 3}
    seg = analytics.segment(c, "R1", "A", "B")["observed"]
    assert seg["dur"] == []                                             # B's visit isn't observed


def test_status_and_segment_use_compact_history(conn, tmp_path):
    ingest = Feeder(conn)
    ingest(trip_update_feed(at(7, 58), {"T1": [(1, at(8, 1), at(8, 1, 30)), (3, at(8, 12), at(8, 12))]}))
    ingest(trip_update_feed(at(8, 12, 50), {"T1": [(3, at(8, 13), at(8, 13, 5))]}))
    client = TestClient(create_app(str(tmp_path / "t.db")))
    ingest._apply([], at(9))                          # final and staged, not merged
    assert client.get("/api/status").json()["observed"] == {"first": "2026-09-21", "last": "2026-09-21", "n": 1, "trips": 1}
    with conn:
        ingest.history.merge_staged()
    assert client.get("/api/status").json()["observed"] == {"first": "2026-09-21", "last": "2026-09-21", "n": 1, "trips": 1}
    assert analytics.segment(conn, "R1", "A", "B", date_from="2026-09-22")["observed"]["dur"] == []


def test_live_state_is_served_from_the_live_database(conn, tmp_path, monkeypatch):
    feeds = {collector.TRIP_UPDATE_URL: trip_update_feed(at(8, 1), {"T1": [(3, at(8, 12), at(8, 12))]}),
             collector.VEHICLE_URL: vehicle_feed(at(8, 1), [("VT1", "T1", at(8, 1), 40.75, -111.89)])}
    monkeypatch.setattr(collector, "fetch_feed", lambda url: feeds[url])
    monkeypatch.setattr(collector.time, "time", lambda: at(8, 1, 5))
    collector.poll_once(conn, collector.StaticLookup(conn))
    assert db.live_path(str(tmp_path / "t.db")).startswith(str(tmp_path))
    client = TestClient(create_app(str(tmp_path / "t.db")))
    [v] = client.get("/api/vehicles/live").json()["vehicles"]
    assert (v["vehicle_id"], v["route_short_name"], v["next_stop_name"], v["delay_s"]) == ("VT1", "1", "Center St / 9th Ave", 120)
    status = client.get("/api/status").json()
    assert status["active_vehicles"] == 1 and status["last_poll"]["n_stop_updates"] == 1
