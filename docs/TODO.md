# TODO

Hosting ([2026-09-22-1159-multi-node-hosting](adr/2026-09-22-1159-multi-node-hosting.md)), in order:

- [ ] Phase 0: healthchecks.io ping from the collector; nightly zstd snapshot of the office DB to R2 (stopgap until the inbox)
- [ ] Phase 1: laptop collector (pinned service, linger, lid switch ignored, Wi-Fi power save off)
- [ ] Phase 2: versioned export (natural ids, `polls.node`, idempotent merge with max `n_updates`), `visits(day)` index, hourly upload to R2 inbox
- [ ] Phase 3: e2-micro merger + `serve` (smaller DayFacts LRU), rebuild-from-R2 script with a tested restore, named Cloudflare Tunnel, $1 budget alert
- [ ] Phase 4: frontend on Cloudflare Pages (configurable API base, CORS), cache rules for finished-day endpoints

Other:

- [ ] Recheck the observed lead window against GPS after a day of 10 s polling
- [ ] Refine observed arrivals with GPS proximity to the stop; would recover the visits outside the lead window (kept since v3)
- [ ] Derive trip-origin departures from GPS (UTA's TripUpdates omit stop_sequence 1)
- [ ] Daily rollup tables if segment payloads get large
- [ ] Buses crossed between two stops, same vs. other route: order of arrival times flips between shared stations (`visits_at`); a prototype took 29 ms for 73 stations
- [ ] Static `corridor` table (shared road between route directions, from `shapes`) for crossings where routes share road but not stops
- [ ] Vehicle continuity: vehicles on several routes, mid-trip swaps (`trip_vehicle`), observed vs. planned `block_id`
- [ ] Delete the pre-v3 backup (`data/uta.db.pre-v3-*.bak.zst`) once v3 has run cleanly for a while
- [ ] Explain the coverage shortfall on Data health: ~27% of scheduled stop visits outside outages are never recorded, beyond first stops
- [ ] Last stops show no realtime either (Red Line's last two stations, every bus bay at Murray Central): confirm in the feed and document next to the first-stop gap
- [ ] Calendar heatmap (day × hour) and before/after a timetable change, once there are weeks of history
