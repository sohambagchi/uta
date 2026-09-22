# Data foundations (schema v2)

- Observed window tightened to lead −120…+15 s; stale visits purged by the collector and by the v2 migration. Rationale: [2026-09-21-2016-observed-lead-window](../adr/2026-09-21-2016-observed-lead-window.md)
- New `stations`, `stops.station_id`, `route_stops`. Rationale: [2026-09-21-2016-stations](../adr/2026-09-21-2016-stations.md)
- New `vehicle_state`; `/api/vehicles/live` reads only active vehicles and takes `routes=`. Rationale: [2026-09-21-2016-live-vehicle-state](../adr/2026-09-21-2016-live-vehicle-state.md)
- Index `stop_events(route_id, stop_id, service_date)` replaces `(route_id, service_date)`.
- Events without a stop are skipped; route falls back to the TripUpdate's `route_id` for trips missing from the static feed.
- Schema versioning via `meta.schema_version` and `db.migrate()`.
