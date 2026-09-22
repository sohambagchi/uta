# Index

## Analysis

- [2026-09-21-2322-claude-design-prompt](analysis-artifacts/2026-09-21-2322-claude-design-prompt.md) — Claude Design brief: question space the data supports and the UI to design for it

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
- [2026-09-22-0025-analytics-dashboard](adr/2026-09-22-0025-analytics-dashboard.md) — pages per level, per-day facts in memory, minimal text
- [2026-09-22-1159-multi-node-hosting](adr/2026-09-22-1159-multi-node-hosting.md) — two local collectors → R2 inbox → merged copy on GCP, Pages frontend via Cloudflare Tunnel

## Changes

- [2026-09-21-2016-data-foundations](changelog/2026-09-21-2016-data-foundations.md) — schema v2
- [2026-09-21-2038-ui-overhaul](changelog/2026-09-21-2038-ui-overhaul.md) — new dashboard
- [2026-09-21-2108-poll-cadence](changelog/2026-09-21-2108-poll-cadence.md) — 10 s polling
- [2026-09-21-2130-subway-design](changelog/2026-09-21-2130-subway-design.md) — subway-map UI overhaul
- [2026-09-21-2200-background-collector](changelog/2026-09-21-2200-background-collector.md) — collector service, migration guard, snapshots
- [2026-09-21-2300-compact-history](changelog/2026-09-21-2300-compact-history.md) — schema v3
- [2026-09-22-0025-analytics-dashboard](changelog/2026-09-22-0025-analytics-dashboard.md) — analytics dashboard
- [2026-09-22-1100-station-search](changelog/2026-09-22-1100-station-search.md) — word-based station search
- [2026-09-22-1130-mobile-pass](changelog/2026-09-22-1130-mobile-pass.md) — phone-width fixes
- [2026-09-22-1145-watch-build](changelog/2026-09-22-1145-watch-build.md) — 2.0.0, frontend rebuilds on change
- [2026-09-22-1605-calendar-everywhere](changelog/2026-09-22-1605-calendar-everywhere.md) — one calendar for every date filter
