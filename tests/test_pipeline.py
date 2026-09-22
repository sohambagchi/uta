"""End-to-end tests on a tiny synthetic GTFS feed + synthetic realtime updates."""

import io
import zipfile
from datetime import date

import pytest
from fastapi.testclient import TestClient
from google.transit import gtfs_realtime_pb2 as rt

from uta import analytics, collector, db, gtfs_static
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


def ingest(conn, feed):
    lookup = collector.StaticLookup(conn)
    with conn:
        conn.executemany(collector.UPSERT_EVENT, list(collector.stop_event_rows(feed, lookup)))


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
    # poll 1: bus approaching A, predictions for A and B
    ingest(conn, trip_update_feed(at(7, 58), {"T1": [(1, at(8, 1), at(8, 1, 30)), (3, at(8, 12), at(8, 12))]}))
    # poll 2: at A (departure updated), B prediction updated
    ingest(conn, trip_update_feed(at(8, 1, 20), {"T1": [(1, at(8, 1), at(8, 1, 40)), (3, at(8, 13), at(8, 13))]}))
    # poll 3: A has left the feed; B imminent
    ingest(conn, trip_update_feed(at(8, 13, 10), {"T1": [(3, at(8, 13, 20), at(8, 13, 30))]}))

    rows = {r["stop_sequence"]: r for r in conn.execute("SELECT * FROM stop_events")}
    assert rows[1]["obs_departure"] == at(8, 1, 40)
    assert rows[1]["n_updates"] == 2
    assert rows[1]["stop_id"] == "A" and rows[1]["route_short_name"] == "1"
    assert rows[1]["sched_arrival"] == at(8)
    assert rows[3]["obs_arrival"] == at(8, 13, 20)
    assert rows[3]["lead_s"] == 10

    res = analytics.travel_time(conn, ["A"], ["B"])
    obs = res["observed"]["overall"]
    assert obs["n"] == 1
    assert obs["median"] == at(8, 13, 20) - at(8, 1, 40)  # 700 s
    assert res["observed_minus_scheduled"]["median"] == 700 - 600
    assert res["observed"]["by_hour"][0]["hour"] == 8
    assert res["observed"]["by_dow"][0]["dow"] == 0


def test_stale_predictions_are_not_observed(conn):
    # only ever saw a far-future prediction for B (e.g. trip dropped from feed)
    ingest(conn, trip_update_feed(at(7, 0), {"T1": [(1, at(8, 0), at(8, 0)), (3, at(8, 10), at(8, 10))]}))
    assert analytics.travel_time(conn, ["A"], ["B"])["observed"]["overall"] is None


def test_scheduled_by_route_and_dow(conn):
    res = analytics.travel_time(conn, ["A"], ["B"])
    sch = res["scheduled"]
    by_route = {r["route"]: r for r in sch["by_route"]}
    assert by_route["1"]["median"] == 600
    assert by_route["2"]["median"] == 1200
    by_dow = {r["dow"]: r for r in sch["by_dow"]}
    # weekday: T1, T2 (10 min) and T3 (20 min) on Mon-Thu
    assert by_dow[0]["weight"] == 3
    assert 4 not in by_dow  # Friday removed by calendar_dates
    # T4 is Saturday service at 25:00 -> departs 1am Sunday
    assert by_dow[6]["n"] == 1 and by_dow[6]["median"] == 600
    hours = {r["hour"] for r in sch["by_hour"]}
    assert hours == {1, 8, 17}

    # filters
    only_r2 = analytics.travel_time(conn, ["A"], ["B"], routes=["2"])["scheduled"]["overall"]
    assert only_r2["median"] == 1200
    peak = analytics.travel_time(conn, ["A"], ["B"], hour_from=17, hour_to=18)["scheduled"]["overall"]
    assert peak["n"] == 4 and peak["median"] == 600


def test_nearby_expansion(conn):
    assert analytics.expand_nearby(conn, ["A"], 50) == ["A", "A2"]
    assert analytics.expand_nearby(conn, ["A"], 0) == ["A"]


def test_stop_search(conn):
    names = [s["stop_id"] for s in analytics.search_stops(conn, "main 1st")]
    assert names == ["A", "A2"]
    downstream = [s["stop_id"] for s in analytics.search_stops(conn, "", downstream_of=["A"])]
    assert set(downstream) == {"M", "B"}


def test_api(conn, tmp_path):
    client = TestClient(create_app(str(tmp_path / "t.db")))
    assert client.get("/api/status").json()["gtfs_feed_version"] == "TEST1"
    r = client.get("/api/travel-time", params={"from": "A", "to": "B"}).json()
    assert r["scheduled"]["overall"]["n"] > 0
    assert client.get("/api/route-performance", params={"route_type": 3}).status_code == 200
    q = client.post("/api/sql", json={"sql": "SELECT COUNT(*) AS n FROM stops"}).json()
    assert q["rows"] == [[4]]
    # the SQL console is read-only
    bad = client.post("/api/sql", json={"sql": "DELETE FROM stops"})
    assert bad.status_code == 400
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


def test_observed_window_and_purge(conn):
    # A left the feed 60 s before its predicted arrival: an early-dropped prediction
    ingest(conn, trip_update_feed(at(7, 59), {"T1": [(1, at(8, 0), at(8, 0)), (3, at(8, 10), at(8, 10))]}))
    ingest(conn, trip_update_feed(at(8, 9, 50), {"T1": [(3, at(8, 10), at(8, 10))]}))
    lead = dict(conn.execute("SELECT stop_sequence, lead_s FROM stop_events"))
    assert lead == {1: 60, 3: 10}
    assert conn.execute("SELECT COUNT(*) FROM observed_stop_events").fetchone()[0] == 1
    # not final yet: nothing purged
    assert db.purge_stale_events(conn, "2026-09-20", now=at(8, 5)) == 0
    assert db.purge_stale_events(conn, "2026-09-20", now=at(9)) == 1
    assert [r[0] for r in conn.execute("SELECT stop_sequence FROM stop_events")] == [3]


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
