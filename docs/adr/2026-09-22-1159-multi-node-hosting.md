# Multi-node hosting: local collectors, R2 inbox, merged copy on a GCP VM

**Status:** accepted (not yet implemented; phases in [TODO](../TODO.md))

**Context:** One collector on one desktop, one copy of the data on one disk, no alert when collection stops. Missed polls can't be backfilled (UTA publishes no realtime archive); everything else can be rebuilt. History grows ~6–8 MB/day (~3 GB/yr) plus ~27 MB of static GTFS per feed version. Budget: free tiers only, on Google and Cloudflare; the user's machines are already on Tailscale and they own a domain on Cloudflare.

**Decision:**
- **Collectors:** office desktop and home laptop (the laptop never sleeps; its battery acts as a UPS; set `HandleLidSwitch=ignore`). Each keeps writing its own local SQLite as today and never waits on the network.
- **R2 inbox is the permanent record:** each collector uploads hourly batches to `inbox/<node>/<day>/<batch>`. Batches are never modified, and the merged database can be rebuilt from them plus GTFS. They also replace local-only backups.
- **Export format**, versioned separately from `SCHEMA_VERSION`:
  - Rows carry natural ids (`stop_id`, `route_id`, `vehicle_id`, `feed_version` + `trip_id`), since local integer keys differ between nodes.
  - The merge is idempotent: newest prediction, earliest first sighting, **max** of `n_updates` (not the sum used locally).
  - GPS is deduplicated by `(vehicle, ts)`, and `trip_vehicle` stretches are combined across nodes.
  - `polls` gets a node column. An outage is when no node polled.
- **GCP e2-micro** runs the merger (every few minutes) and `uta serve` read-only against the merged copy, with the `DayFacts` LRU cut to ~10–14 days for 1 GB RAM. It does no collecting at first; measure before adding it as a third collector. It never uploads backups, because R2 already holds the history and egress is limited.
- **Public access through a named Cloudflare Tunnel** on the existing domain (outbound-only from the VM, no open ports). CORS is limited to the frontend's origin. Cache rules on finished-day API responses keep repeat views off the VM.
- **Frontend on Cloudflare Pages** with a configurable API base. It stays up when the VM is down.
- **Tailscale for private access:** SSH, admin and ad-hoc copies between the three machines. It is not on the data path.
- **Monitoring:** each collector checks in with healthchecks.io every minute. A $1 GCP budget alert.
- **Upgrades:** one collector at a time, so one is always polling.

**Alternatives:**
- **Collectors write directly to a remote database:** rejected, because every network or host blip would become a permanent gap.
- **Managed Postgres (Neon, Supabase):** rejected. Free tiers of about 0.5 GB would fill in months, and they pause when idle.
- **D1 or Turso:** rejected, because row-metered reads don't suit scanning a whole day.
- **Redis cache:** rejected. Finished days are immutable, so HTTP and CDN caching is enough.
- **Vercel for the frontend:** Pages keeps everything on Cloudflare.
- **Tailscale Funnel as the public link:** not needed, since there is a domain and the Tunnel is on it.
- **Oracle Always Free:** declined in favour of Google and Cloudflare.
- **Fully static frontend reading from R2:** deferred. It would mean porting `insights.py` to rollups or to the browser. Revisit only if the VM proves unreliable.

**Consequences:**
- The public site depends on the VM. Collection does not.
- About 1 GB/month of GCP egress in North America (verify current terms) limits API traffic, so CDN caching matters.
- The VM's external IPv4 may be billed. Check it after the first days.
- R2's free 10 GB holds about 3 years of batches, after which they need compaction or tiering.
- Both collectors must import the same GTFS `feed_version`. The merger rejects batches with an unknown version.
- The export format becomes a compatibility contract between nodes running different builds.
