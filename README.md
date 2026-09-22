# UTA Transit Explorer

A local-first dashboard and database for Utah Transit Authority buses and trains. It builds its own
history from UTA's public feeds, so you can ask questions like:

- How long does it take to get from stop A to stop B, **on average**?
- How does that vary by **time of day** and **day of week**?
- Which **routes** between A and B are fastest, and how do they compare with the timetable?
- Which routes run late, and at what hours? What are the real headways at my stop?
- Anything else, via a read-only **SQL console** over the whole database.

## Quick start

Needs Nix with flakes (Determinate Nix has them on by default).

```sh
nix run . -- up            # import GTFS, start collector + dashboard on http://127.0.0.1:8000
```

Or, from a dev shell:

```sh
nix develop
python -m uta import-gtfs  # one-off: download + load the static timetable (~10 s)
python -m uta collect      # poll realtime feeds every 30 s (leave running)
python -m uta serve        # dashboard at http://127.0.0.1:8000 (separate terminal)
pytest                     # tests
sqlite3 data/uta.db        # query directly
```

The database lives at `./data/uta.db`. Override it with `--db` or `$UTA_DB`.

**History only exists from when the collector starts.** UTA doesn't publish archived realtime
data, so run `collect` (or `up`) continuously. Scheduled-time answers work immediately. Observed
answers fill in as data accumulates: a few days gives usable hour-of-day patterns, and a few
weeks gives good day-of-week comparisons.

## Data sources

All from UTA's open GTFS endpoints; no API key needed.

| Feed | URL | Used for |
|---|---|---|
| Static GTFS | `https://apps.rideuta.com/tms/gtfs/Static` | routes, stops, timetable, shapes (re-checked every 6 h, re-imported when the version changes) |
| TripUpdates | `https://apps.rideuta.com/tms/gtfs/TripUpdate` | predicted/actual arrival per trip and stop, which becomes observed travel times |
| VehiclePositions | `https://apps.rideuta.com/tms/gtfs/Vehicle` | live map, GPS history |

### How observed times are derived

UTA's TripUpdates list predictions for the current and upcoming stops of each active trip, and a
stop drops out once the vehicle has passed it. The collector upserts every (trip, stop)
prediction on each poll, so the **last value seen for a stop is the prediction made as the bus was
there**, which is effectively the actual time. `lead_s` records how far in the future that final
prediction was when we last saw it. Visits with `lead_s <= 120` count as observed; the rest
(cancelled trips, collector downtime) are excluded. In testing, about 80% of completed visits had a
final lead within ±60 s.

Every stop visit also carries the scheduled time from the GTFS in effect when it was recorded, plus
route and stop details. History therefore stays meaningful after UTA publishes a new timetable.

## Database

SQLite (WAL mode, safe to read while the collector writes). Local time is America/Denver.

| Table / view | What it holds |
|---|---|
| `stop_events` | one row per trip × stop visit: observed and scheduled arrival/departure (epoch s), route, vehicle, `lead_s` |
| `observed_stop_events` (view) | `stop_events` filtered to real observations, plus `delay_s`, `hour`, `dow` (0 = Mon), stop name |
| `vehicle_positions` | GPS pings (vehicle, trip, route, lat/lon, speed m/s, bearing) |
| `polls` | collector health log |
| `routes`, `stops`, `trips`, `stop_times`, `shapes` | current static GTFS (`stop_times` in seconds after service-day midnight) |
| `service_dates` | every date each `service_id` runs (calendar + exceptions expanded) |
| `stop_routes` | which routes and directions serve each stop |
| `scheduled_stop_times` (view) | `stop_times` joined with trip, route, and stop names |

Example: average observed minutes from stop `5502` to `21929` by route and hour:

```sql
SELECT a.route_short_name AS route, a.hour, COUNT(*) AS trips,
       ROUND(AVG(b.obs_arrival - a.obs_departure) / 60.0, 1) AS avg_min
FROM observed_stop_events a
JOIN observed_stop_events b
  ON b.service_date = a.service_date AND b.trip_id = a.trip_id AND b.stop_sequence > a.stop_sequence
WHERE a.stop_id = '5502' AND b.stop_id = '21929'
GROUP BY route, a.hour;
```

The SQL tab in the dashboard has more examples: headways, slowest segments, adherence by route,
and GPS speed by hour.

## Dashboard

- **Travel time**: pick From/To stops (search by name, street or stop code; the To list is limited
  to stops reachable directly). You can merge nearby stops, such as both sides of a street or
  several platforms. Filter by weekday, hour, or date range; toggle routes. You get observed vs
  scheduled medians with p10–p90 spread, broken down by hour, day, day×hour, and route, plus
  recent individual trips. Filters are kept in the URL, so views can be bookmarked.
- **Route performance**: on-time % (from 1 min early to 5 min late) by hour, and average delay by route.
- **Live map**: vehicles colored by delay or route color, with route shapes.
- **SQL**: read-only queries with a 15 s timeout and a 5,000-row cap, plus a schema browser.

JSON API: `/api/travel-time`, `/api/route-performance`, `/api/stops`, `/api/routes`,
`/api/vehicles/live`, `/api/sql`, `/api/status`. See `/docs` for the OpenAPI UI.

## Storage

The static GTFS is about 32 MB. The collector adds about 250k stop events a day plus about 800k
GPS pings, roughly 100 MB a day. Use `collect --no-positions` to skip GPS history if you only
need travel times; stop events alone are a fraction of that.

## Known limitations (MVP)

- Direct trips only. A→B journeys needing a transfer aren't computed.
- Observed accuracy is bounded by UTA's predictions and the 30 s poll interval (typically ±30–60 s).
  Refining arrivals with GPS proximity to the stop is a natural next step.
- A small share of realtime trip IDs (under 1% so far) aren't in the published static feed. Those
  visits are stored without route or schedule info.
- Leaflet and map tiles load from the internet. Everything else is local.

## Layout

```
flake.nix               nix package, `nix run`, dev shell
src/uta/db.py           schema + views
src/uta/gtfs_static.py  static GTFS download/import
src/uta/collector.py    realtime polling → stop_events / vehicle_positions
src/uta/analytics.py    travel-time and performance queries
src/uta/server.py       FastAPI app
src/uta/static/         dashboard (vanilla JS, hand-rolled SVG charts)
tests/                  synthetic-feed tests for import, ingestion, and analytics
```
