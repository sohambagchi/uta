# Compact history (schema v3): keys and offsets, write each visit once, GPS in compressed blocks

**Status:** accepted (supersedes the deletion part of [2026-09-21-2016-observed-lead-window](2026-09-21-2016-observed-lead-window.md))

**Context:** Measured on 2026-09-21, on a copy of 6.7 h of history:
- **Size:** `stop_events` cost 231 B a visit (145 B row + two indexes of text keys). `vehicle_positions` cost 89 B a ping, and nothing in the app reads it. About 100 MB a weekday, 35 GB a year.
- **Writes:** the collector wrote about 13 GB a day to hold that 100 MB. On every poll it rewrote about 1,900 in-flight predictions spread across the day's pages (179 pages), made ~45 random GPS inserts (61 pages), and rewrote `vehicle_state` (8 pages). WAL checkpoints then write each page a second time.
- **Status query:** `/api/status` counted over all of `stop_events` every 30 s per open tab.
- **Coming queries** need access paths the old layout doesn't have: active buses per route; buses crossed between two stops, same vs. other route; buses on several routes; vehicle continuity over a trip or block. They need visits by (stop, time), the vehicle TripUpdates assigns each trip, and block ids from the timetable in use at the time.

**Decision:**
- **Visits** (`visits`, WITHOUT ROWID, primary key `(route, stop, day, trip, seq)`):
  - Ids become integer keys (`stop_keys`, `route_keys`, `vehicle_keys`). `trip_dim` holds one row per distinct trip version, including `block_id`, `shape_id`, `service_id` and feed version.
  - Times are offsets: arrival in seconds after the service day's origin (`days.origin`), then delay, dwell, scheduled dwell, `lead_s`, and the first-to-last-sighting span.
  - The segment query is two primary-key range scans. `visits_at(stop, day, arr)` serves "what passed this stop between t0 and t1".
  - About 58 B a visit with both.
- **Write once:**
  - The collector keeps in-flight visits in memory (`collector.Tracker`). It writes a visit after it has been out of the feed for 60 s, appending it to `visits_new`.
  - Every 6 h, `visits_new` is merged into `visits` in key order. Readers union the two (`visits_all`).
  - A visit that comes back after being written is merged: newest prediction, earliest first sighting, summed update count.
- **Keep all visits:** visits outside the observed window are no longer deleted. `observed()` filters them at query time. They cost about 60 B each and carry vehicle and timing data for continuity and crossing queries.
- **`trip_vehicle`:** one row per stretch of a trip run by one vehicle, taken from the TripUpdates vehicle id. The vehicle feed sometimes names a vehicle's next trip early: 133 of 1,901 trips showed 2+ vehicles in GPS, versus 1 in visits.
- **GPS:**
  - Pings append to `gps_recent` (key `(ts, vehicle)`). Each ping stores both the vehicle feed's trip and TripUpdates' trip.
  - Every closed day is sealed into `gps_blocks`: one zstd-compressed, delta-coded columnar block per (day, vehicle).
  - Floats are float32 in the feed, so they are stored as exact integer codes: lat/lon × 2¹⁸, bearing × 100, speed in 0.01 mph. A value that doesn't round-trip, or is NULL, is stored as a raw exception.
  - `gps.read()` returns the original rows. Still one ping per vehicle per 30 s.
- **Batching:**
  - Final visits, trip vehicles, GPS, and the poll log are committed every 60 s.
  - In-flight state (zstd JSON in `collector_state`) is saved every 5 min and on SIGTERM.
  - `vehicle_state` and the latest poll move to a live database in `$XDG_RUNTIME_DIR` (tmpfs).
- **Status counts:** `day_stats` (from `trip_days`) plus a count over `visits_new` answers `/api/status` in constant time.
- **Backups:** pre-migration backups are zstd-compressed (4.4× smaller); the newest 3 are kept.
- **Migration v2 → v3:** runs in one transaction and converts through the same writer as the collector. It checks that `stop_events` rebuilt from `visits` equals the original table (`EXCEPT` both ways) and that decoded GPS equals `vehicle_positions`, and rolls back otherwise. Pre-v3 `trip_vehicle` rows are rebuilt from visits, so they only see each visit's final vehicle.

**Measured** (copy of the live database, 2026-09-21 evening):

| | v2 | v3 |
|---|---|---|
| bytes per visit (with indexes) | 231 | 58 |
| bytes per GPS ping | 89 | 8.1 sealed (partial day; blob alone 5.8) |
| collector disk writes | 124 KB/s | 1.75 KB/s + about 0.3 KB/s for the 6-hourly merge |
| segment query (same result) | 0.35 ms | 0.11 ms |
| crossings for one trip, 73 stations | not supported | 29 ms |

Migration of 50k visits and 200k pings took 4.8 s. The database went from 61 MB to 42 MB before any GPS was sealed; about 35 MB of what remains is the static GTFS.

**Alternatives:**
- **Insert each visit into `visits` as it finishes.** Rejected: pages written per hour of data were 39 MB when writing every poll, 8 MB every 15 min, 2.7 MB hourly, and 0.5 MB every 6 h. The per-poll cost also grows as history grows.
- **Keep in-flight or final visits only in memory until a merge.** Rejected: the checkpoint would then carry hours of visits.
- **Store delay instead of arrival time.** One byte smaller, but "at this stop between t0 and t1" couldn't use an index.
- **Columnar blocks for visits too** (about 6 B a visit). The segment query would need a new read path; 58 B is small enough for now.
- **Keep GPS every 10 s.** Declined for now; 30 s stays.

**Consequences:**
- History is not visible in the database until a visit has been out of the feed for 60 s and its batch is committed (≤ 60 s later). A crash loses at most 60 s of GPS and poll log, plus the in-flight updates since the last 5-minute checkpoint. Those stops are still in the feed after a restart, so what is lost is their `first_seen` and `n_updates`.
- Ad-hoc SQL uses the `stop_events` and `observed_stop_events` views as before. GPS history is read through `uta.gps.read`, not SQL, once a day is sealed.
- Requires Python 3.14 (`compression.zstd`).
- The live view is empty after a reboot until the collector's first poll.
- Upgrading the pinned collector runs the migration: the database is backed up, converted, and VACUUMed while collection is paused for the few seconds it takes.
