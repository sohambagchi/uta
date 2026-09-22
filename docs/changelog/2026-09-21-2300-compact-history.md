# Compact history (schema v3)

- `stop_events` table → `visits` (integer keys, time offsets, clustered by route/stop/day) + `visits_new` staging; `stop_events` is now a view with the same columns. The segment query reads `visits` directly.
- Visits outside the observed window are kept (no more purge); `observed()` filters them.
- Collector writes each visit once, after it has left the feed (`collector.Tracker`); commits every 60 s; merges staged visits every 6 h; saves in-flight state every 5 min and on SIGTERM/Ctrl-C.
- New `trip_dim` (trip route/headsign/block/shape/service as observed), `trip_vehicle` (vehicle per trip stretch, from TripUpdates), `trip_days` / `day_stats`, `visits_at(stop, day, arr)` index.
- `vehicle_positions` → `gps_recent` + `gps_blocks` (zstd columnar per vehicle-day, lossless); pings also record the TripUpdates trip. Read with `gps.read`.
- `vehicle_state` and the latest poll moved to a live database in `$XDG_RUNTIME_DIR` (`db.live_path`); `/api/vehicles/live` and `/api/status` read it.
- `/api/status` no longer scans history.
- Migration backups are zstd (`.bak.zst`), newest 3 kept.
- Python ≥ 3.14.
- Rationale: [2026-09-21-2300-compact-history](../adr/2026-09-21-2300-compact-history.md)
