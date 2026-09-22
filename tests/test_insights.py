"""The dashboard query layer (insights.py) on the synthetic feed from test_pipeline."""

from fastapi.testclient import TestClient

from uta import insights
from uta.server import create_app

from test_pipeline import Feeder, at, conn, live_dir, trip_update_feed  # noqa: F401 (fixtures)


def ride_t1(conn, late_b=200):
    """T1 observed at A (on time) and B (late_b seconds late); T3 never observed."""
    ingest = Feeder(conn)
    ingest(trip_update_feed(at(7, 58), {"T1": [(1, at(8, 0), at(8, 0, 30)), (3, at(8, 12), at(8, 12))]}))
    ingest(trip_update_feed(at(8, 0, 10), {"T1": [(1, at(8, 0), at(8, 0, 30)), (3, at(8, 12), at(8, 12))]}))
    ingest(trip_update_feed(at(8, 13, 10), {"T1": [(3, at(8, 10) + late_b, at(8, 10) + late_b)]}))
    ingest.flush(at(9))
    conn.executemany("INSERT INTO polls (ts, feed_ts) VALUES (?, ?)", [(at(7, 50) + 10 * i, at(7, 50) + 10 * i - 4)
                                                                      for i in range(6 * 80)])
    conn.commit()


def client(tmp_path):
    return TestClient(create_app(str(tmp_path / "t.db")))


def test_delay_stats_window():
    s = insights.delay_stats([-120, 0, 60, 301, 400])
    assert s["n"] == 5 and s["otp"] == 2 / 5 and s["early"] == 1 / 5 and s["late"] == 2 / 5 and s["median"] == 60


def test_modes():
    assert insights.mode_of(2, "750") == "rail"
    assert insights.mode_of(0, "701") == "lrt" and insights.mode_of(0, "720") == "streetcar"
    assert insights.mode_of(3, "200") == "bus"


def test_network_summary(conn, tmp_path):
    ride_t1(conn)
    n = client(tmp_path).get("/api/insights/network").json()
    assert n["scope"]["from"] == n["scope"]["to"] == "2026-09-21"
    assert n["kpi"]["n"] == 2 and n["kpi"]["median"] == 100
    [r1] = n["routes"]
    assert r1["short"] == "1" and r1["trips"] == 1 and r1["otp"] == 1.0
    # hour filter drops everything outside 9-10
    assert client(tmp_path).get("/api/insights/network", params={"h": "9-10"}).json()["kpi"]["n"] == 0
    # T1 and T3 run 8:00-8:50 inside the polled window; only T1 was observed
    assert n["kpi"]["service"] == {"scheduled": 2, "observed": 1, "in_gaps": 0}


def test_route_marey_and_accumulation(conn, tmp_path):
    ride_t1(conn, late_b=200)
    r = client(tmp_path).get("/api/insights/route/R1/0").json()
    assert [s["station_id"] for s in r["stations"]] == ["A", "M", "B"]
    assert [a["n"] for a in r["acc"]] == [1, 0, 1]
    assert r["acc"][2]["median"] == 200
    [m] = r["marey"]["trips"]
    assert m["trip_id"] == "T1" and [p[0] for p in m["obs"]] == [0, 2]
    # T2 (17:00) is timetabled but never observed
    assert [t["trip_id"] for t in r["marey"]["sched_only"]] == ["T2"]
    assert r["runtime"]["trips"][0]["obs"] == at(8, 10) + 200 - at(8, 0, 30)
    assert client(tmp_path).get("/api/insights/route/nope/0").status_code == 404


def test_station_trip_vehicle_and_search(conn, tmp_path):
    ride_t1(conn)
    c = client(tmp_path)
    s = c.get("/api/insights/station/A").json()
    assert s["station"]["name"].startswith("Main St")
    assert {x["short"] for x in s["routes"]} == {"1"}
    assert s["board"][0]["trip_id"] == "T1"
    t = c.get("/api/insights/trip/T1").json()
    assert [x["observed"] for x in t["stops"]] == [True, False, True]
    assert t["vehicles"][0]["vehicle_id"] == "VT1"
    v = c.get("/api/insights/vehicle/VT1").json()
    assert [x["trip_id"] for x in v["trips"]] == ["T1"] and v["trips"][0]["d_last"] == 200
    assert c.get("/api/insights/vehicle/nope").status_code == 404
    found = c.get("/api/search", params={"q": "center"}).json()
    assert found["stations"][0]["name"].startswith("Center St")
    assert c.get("/api/search", params={"q": "VT"}).json()["vehicles"] == ["VT1"]


def test_health_coverage_and_gaps(conn, tmp_path):
    ride_t1(conn)
    h = client(tmp_path).get("/api/insights/health").json()
    assert h["kpi"]["polls"] == 480 and h["kpi"]["lag_median"] == 4
    assert h["gaps"] == []
    # scheduled in the polled window: T1 at A, M, B and T3 at A, B; recorded: T1 at A and B
    assert h["network_share"] == 2 / 5 and h["first_stops"] == 2
    assert h["maturity"]["days"] == 1 and h["maturity"]["by_dow"][0] == 1


def test_headways_skip_collector_outages():
    # three arrivals 10 min apart as scheduled; an outage between the 2nd and 3rd
    m = [{"obs": [[0, t, 0]]} for t in (1000, 1600, 2200)]
    sched = {"a": [[0, 1000]], "b": [[0, 1600]], "c": [[0, 2200]]}
    h = insights.headway_stats(m, sched, 0, (0, 5000), [[1700, 1900]])
    assert [g["spans_missing"] for g in h["obs"]] == [False, True]
    assert h["stats"]["n"] == 1 and h["stats"]["ewt"] == 0


def test_vehicle_gps_and_route_feeds(conn, tmp_path):
    ride_t1(conn)
    c = client(tmp_path)
    g = c.get("/api/insights/vehicle/VT1/gps").json()
    assert g["vehicle_id"] == "VT1" and g["pings"] == []        # the synthetic feed has no GPS
    assert c.get("/api/insights/vehicle/nope/gps").status_code == 404
    r = c.get("/api/insights/route/R1/0").json()
    assert r["feeds"] == [{"version": "TEST1", "trips": 1, "first": "2026-09-21", "last": "2026-09-21"}]
    # a mode filter that excludes buses leaves the station with no route rows
    assert c.get("/api/insights/station/A", params={"modes": "rail"}).json()["routes"] == []


def test_time_of_day_scopes_every_station_panel(conn, tmp_path):
    ride_t1(conn)
    c = client(tmp_path)
    assert c.get("/api/insights/station/A").json()["board"]
    assert c.get("/api/insights/station/A", params={"h": "9-12"}).json()["board"] == []


def test_default_scope_is_the_whole_span(conn, tmp_path):
    ride_t1(conn)
    # a second service day of history
    conn.execute("INSERT INTO days (day, service_date, origin) VALUES (?, ?, ?)", (insights.day_number("2026-09-23"), "2026-09-23", at(0) + 2 * 86400))
    conn.execute("INSERT INTO day_stats (day, n_visits, n_observed, n_trips) VALUES (?, 5, 5, 1)", (insights.day_number("2026-09-23"),))
    conn.commit()
    sc = client(tmp_path).get("/api/insights/network").json()["scope"]
    assert (sc["from"], sc["to"]) == ("2026-09-21", "2026-09-23")
    sc = client(tmp_path).get("/api/insights/network", params={"to": "2026-09-21"}).json()["scope"]
    assert (sc["from"], sc["to"]) == ("2026-09-21", "2026-09-21")
