# Live views read a per-poll vehicle_state table

**Status:** accepted

**Context:** The live endpoint searched `vehicle_positions` history, plus one lookup against `stop_events` per vehicle with no index (1.7 s after 4 h of data, getting worse). The vehicle feed also names the next trip in the block for about 24% of vehicles while TripUpdates still predicts the current one.
**Decision:** The collector replaces `vehicle_state` on every poll, keeping only vehicles on a trip that reported within 180 s. Trip, delay, and next stop come from TripUpdates (matched by vehicle id), with the vehicle feed as fallback. Live endpoints read only this table and apply a wall-clock age check.
**Consequences:** Live queries take about 30 ms. If the collector stops, the live view empties instead of showing stale vehicles. `vehicle_positions` stays history only.
