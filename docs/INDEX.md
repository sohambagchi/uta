# Index

## Decisions

- [2026-09-21-2016-observed-lead-window](adr/2026-09-21-2016-observed-lead-window.md) — what counts as an observed stop visit (deletion superseded by v3)
- [2026-09-21-2016-stations](adr/2026-09-21-2016-stations.md) — stop → station grouping
- [2026-09-21-2016-live-vehicle-state](adr/2026-09-21-2016-live-vehicle-state.md) — live views read only active vehicles
- [2026-09-21-2038-route-segments](adr/2026-09-21-2038-route-segments.md) — analytics model: route segments, stats in the browser
- [2026-09-21-2038-web-build](adr/2026-09-21-2038-web-build.md) — Svelte + Vite dashboard, built by Nix
- [2026-09-21-2038-maplibre](adr/2026-09-21-2038-maplibre.md) — MapLibre + OpenFreeMap map
- [2026-09-21-2108-poll-cadence](adr/2026-09-21-2108-poll-cadence.md) — poll every 10 s, skip stale snapshots
- [2026-09-21-2130-subway-design](adr/2026-09-21-2130-subway-design.md) — NYC-subway visual design, light by default
- [2026-09-21-2200-background-collector](adr/2026-09-21-2200-background-collector.md) — collector as a pinned service; only it migrates
- [2026-09-21-2300-compact-history](adr/2026-09-21-2300-compact-history.md) — schema v3: compact visits written once, trip vehicles, GPS blocks, tmpfs live state

## Changes

- [2026-09-21-2016-data-foundations](changelog/2026-09-21-2016-data-foundations.md) — schema v2
- [2026-09-21-2038-ui-overhaul](changelog/2026-09-21-2038-ui-overhaul.md) — new dashboard
- [2026-09-21-2108-poll-cadence](changelog/2026-09-21-2108-poll-cadence.md) — 10 s polling
- [2026-09-21-2130-subway-design](changelog/2026-09-21-2130-subway-design.md) — subway-map UI overhaul
- [2026-09-21-2200-background-collector](changelog/2026-09-21-2200-background-collector.md) — collector service, migration guard, snapshots
- [2026-09-21-2300-compact-history](changelog/2026-09-21-2300-compact-history.md) — schema v3
