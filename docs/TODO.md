# TODO

- [ ] Recheck the observed lead window against GPS after a day of 10 s polling
- [ ] Refine observed arrivals with GPS proximity to the stop; would recover the visits outside the lead window (kept since v3)
- [ ] Derive trip-origin departures from GPS (UTA's TripUpdates omit stop_sequence 1)
- [ ] Route pages: per-stop delay accumulation, headway regularity, bunching
- [ ] Daily rollup tables if segment payloads get large
- [ ] Active buses per route (now: live `vehicle_state`; past: `trip_vehicle` overlapping t)
- [ ] Buses crossed between two stops, same vs. other route: order of arrival times flips between shared stations (`visits_at`); a prototype took 29 ms for 73 stations
- [ ] Static `corridor` table (shared road between route directions, from `shapes`) for crossings where routes share road but not stops
- [ ] Vehicle continuity: vehicles on several routes, mid-trip swaps (`trip_vehicle`), observed vs. planned `block_id`
- [ ] Delete the pre-v3 backup (`data/uta.db.pre-v3-*.bak.zst`) once v3 has run cleanly for a while
