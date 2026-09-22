# Observed stop visits: lead window −120…+15 s, stale visits deleted

**Status:** accepted

**Context:** A visit's stored time is the last prediction seen before the stop left the feed. The old rule (`lead_s <= 120`) accepted visits that dropped out early or lingered long after arrival. GPS check on 2026-09-21 data: distance from vehicle to stop at the recorded time, by final lead:

| lead_s | median | within 300 m |
|---|---|---|
| −1200…−120 | 156–199 m | 63–74% |
| −120…−60 | 120 m | 83% |
| −60…0 | 74–84 m | 89–96% |
| 0…15 | 161 m | 83% |
| 15…30 | 236 m | 65% |
| 30…60 | 342–424 m | 27–43% |

**Decision:** Observed = `lead_s BETWEEN -120 AND 15` (`db.OBS_LEAD_MIN/MAX`). The collector deletes visits outside the window once they have been out of the feed for 10 min (`FINAL_AFTER_S`), scanning the last two service days every 5 min. Visits with no resolvable stop are never stored.
**Alternatives:** Keep everything and filter at query time. Rejected: stale rows cost storage and every query has to repeat the filter. GPS-refined arrival times would recover the discarded visits, but they're a larger project (see TODO).
**Consequences:** About 34% of visits are discarded. The schema v2 migration deleted them from existing data, which can't be undone.
