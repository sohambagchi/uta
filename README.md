# UTA Transit Explorer

A local-first analytics dashboard for Utah Transit Authority buses and trains. It builds its own
history from UTA's public feeds, then lets you pick a route and two of its stops and see how long
that stretch actually takes:

- the typical trip, the spread (p10–p90, p95, std dev, CV, buffer index), and the timetable,
- how it varies by **time of day**, **day of week**, and **day by day**,
- up to **four segments side by side**: different routes over the same stops, or different
  stretches of one route,
- every vehicle currently in service on a live map, colored by delay.

## Quick start

Needs Nix with flakes (Determinate Nix has them on by default).

```sh
nix run . -- up            # import GTFS, start collector + dashboard on port 8000, all interfaces
```

`up` listens on `0.0.0.0` so other devices on your network can open the dashboard; pass
`--host 127.0.0.1` to keep it local. `serve` binds to `127.0.0.1` by default.

**History only exists from when the collector starts.** UTA doesn't publish archived realtime
data, so run `collect` (or `up`) continuously. Timetable figures work immediately. Observed ones
fill in as data accumulates: a few days gives usable time-of-day patterns, and a few weeks gives
good day-of-week comparisons.

### Collector as a background service

For long-running collection, run the collector on its own as a systemd user service, separate
from the dashboard, so development never interrupts it:

```sh
deploy/install-collector.sh      # build a pinned copy, install + start uta-collector.service
loginctl enable-linger $USER     # once: keep it running when logged out / after reboot
journalctl --user -u uta-collector -f
```

The service runs a build pinned at `~/.local/state/uta/collector`, so later `nix build`s and
edits in the checkout don't affect it. Re-run the script to upgrade it to the current checkout.
The dashboard is then just `serve` (from the pinned build or the dev shell) against the same
database. See the [ADR](docs/adr/2026-09-21-2200-background-collector.md).

## Development

Everything runs through the flake's dev shell, which provides Python, Node, and sqlite.

```sh
nix develop
python -m uta import-gtfs        # one-off: download + load the static timetable (~10 s)
python -m uta collect            # poll realtime feeds every 10 s (or use the service above)
python -m uta serve              # API + built dashboard on :8000 (read-only, never migrates)
python -m uta snapshot           # consistent copy of the live database into data/dev.db
npm --prefix web install         # once
npm --prefix web run dev         # dashboard with hot reload on :5173, proxies /api to :8000
npm --prefix web run build       # build into src/uta/static/ (what `serve` hosts)
npm --prefix web run check       # svelte-check / TypeScript
pytest                           # backend tests
nix build                        # full package: builds web/ and runs pytest
```

The database lives at `./data/uta.db`. Override it with `--db` or `$UTA_DB`.

**Protecting collected data.** `serve` reads the database through read-only connections and
refuses to start if the database needs a migration (pass `--migrate` to override). Migrations
belong to the collector (`collect` / `up`), which first backs the database up to
`uta.db.pre-vN-<time>.bak`. Every command refuses a database with a newer schema than it knows,
so an old pinned collector won't write into a database a newer build migrated. When working on
schema or query changes, develop against a snapshot:
`python -m uta snapshot && UTA_DB=data/dev.db python -m uta serve --migrate`.

After changing `web/package-lock.json`, update `npmDepsHash` in `flake.nix`. `nix build .#web`
prints the new hash.

Project docs (decisions, changelog, TODO) live in [docs/](docs/INDEX.md). Commits are numbered
`[X.Y.Z]` (see [CLAUDE.md](CLAUDE.md)).

## Data sources

All from UTA's open GTFS endpoints; no API key needed.

| Feed | URL | Used for |
|---|---|---|
| Static GTFS | `https://apps.rideuta.com/tms/gtfs/Static` | routes, stops, timetable, shapes (re-checked every 6 h, re-imported when the version changes) |
| TripUpdates | `https://apps.rideuta.com/tms/gtfs/TripUpdate` | predicted/actual arrival per trip and stop, which becomes observed travel times; live delay |
| VehiclePositions | `https://apps.rideuta.com/tms/gtfs/Vehicle` | live map, GPS history |

The basemap uses [OpenFreeMap](https://openfreemap.org) vector tiles. Everything else is served
locally.

### How observed times are derived

UTA's TripUpdates list predictions for the current and upcoming stops of each active trip, and a
stop drops out once the vehicle has passed it. The collector upserts every (trip, stop)
prediction on each poll, so the **last value seen for a stop is the prediction made as the bus was
there**, which is effectively the actual time. `lead_s` records how far in the future that final
prediction was when we last saw it.

Visits with `lead_s` between −120 and +15 s count as observed. Checked against GPS, the vehicle is
a median of about 90 m from the stop at those times. Once a visit is final, the collector deletes
it if it falls outside that window (early-dropped or stale predictions, cancelled trips, collector
downtime). See the [ADR](docs/adr/2026-09-21-2016-observed-lead-window.md).

UTA never publishes realtime data for a trip's first stop, so segments starting at a route's
origin have timetable figures only.

Every stop visit also carries the scheduled time from the GTFS in effect when it was recorded, plus
route and stop details. History therefore stays meaningful after UTA publishes a new timetable.

## Dashboard

- **Left column:** up to four comparisons. Each has a route, a direction, and two stops, picked
  from the route's ordered stop list or by clicking stops on the map. Duplicate a comparison and
  change its route to compare the same stops on another route. Stops are grouped into
  [stations](docs/adr/2026-09-21-2016-stations.md), so bays of one hub and both sides of a street
  count as the same place.
- **Map:** every vehicle currently on a trip, animated between polls. Vehicles on compared routes
  are colored by delay and point in their direction of travel. The map also shows the active
  route, each comparison's segment in its color, and the route network. Drag the bar under the
  map to resize it.
- **Filters** (apply to everything below them): history window, weekdays, departure-hour range,
  time-of-day bin size, far-outlier exclusion.
- **Travel time table:** trips, median, mean, p10–p90, p95, std dev, CV, buffer index, timetable
  median and trips per week, and observed minus scheduled.
- **Charts:** distribution (share of trips within X minutes), median by time of day with a p10–p90
  band and the timetable, variability by time of day, versus timetable, by day of week, day by
  day, and every trip as a dot.
- **Trips table:** the individual trips behind the active comparison.

Comparisons and filters are kept in the URL, so views can be bookmarked.

JSON API: `/api/routes`, `/api/routes/{route_id}`, `/api/segment`, `/api/network`,
`/api/vehicles/live`, `/api/status`. See `/docs` for the OpenAPI UI. `/api/segment` returns
per-trip samples; the dashboard filters and summarizes them in the browser.

## Database

SQLite (WAL mode, safe to read while the collector writes). Local time is America/Denver.

| Table / view | What it holds |
|---|---|
| `stop_events` | one row per trip × stop visit: observed and scheduled arrival/departure (epoch s), route, vehicle, `lead_s` |
| `observed_stop_events` (view) | `stop_events` filtered to observed visits, plus `delay_s`, `hour`, `dow` (0 = Mon), stop name |
| `vehicle_positions` | GPS pings (vehicle, trip, route, lat/lon, speed m/s, bearing) |
| `vehicle_state` | vehicles on a trip in the latest poll, with delay and next stop (live views) |
| `polls` | collector health log |
| `routes`, `stops`, `trips`, `stop_times`, `shapes` | current static GTFS (`stop_times` in seconds after service-day midnight) |
| `service_dates` | every date each `service_id` runs (calendar + exceptions expanded) |
| `stop_routes` | which routes and directions serve each stop |
| `stations`, `stops.station_id` | stops grouped into stations |
| `route_stops` | ordered stations along each route direction |
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

## Storage

The static GTFS is about 32 MB. The collector adds about 160k observed stop events a day plus
about 800k GPS pings (one per vehicle per 30 s), roughly 100 MB a day. Use `collect --no-positions`
to skip GPS history; the live map doesn't need it.

UTA regenerates both realtime feeds about every 10 s, so the collector polls every 10 s and the
live map refreshes at the same rate ([ADR](docs/adr/2026-09-21-2108-poll-cadence.md)).

## Layout

```
flake.nix               nix package (web + python), `nix run`, dev shell
src/uta/db.py           schema, migrations, observed window
src/uta/gtfs_static.py  static GTFS import; derives stations and route_stops
src/uta/collector.py    realtime polling → stop_events / vehicle_state / vehicle_positions
src/uta/analytics.py    route, segment, and network queries
src/uta/server.py       FastAPI app
deploy/                 systemd user service installer for the collector
web/                    Svelte + TypeScript dashboard (Vite, MapLibre GL, Observable Plot)
tests/                  synthetic-feed tests for import, ingestion, and queries
docs/                   ADRs, changelog, TODO
```
