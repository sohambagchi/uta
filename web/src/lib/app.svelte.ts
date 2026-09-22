// App-wide data: service days with history and collector status, refreshed in the background.

import { api, insights, type DayInfo, type NetworkLine, type Route, type Status } from "./api";

class AppData {
  days = $state<DayInfo[]>([]);
  status = $state<Status | null>(null);
  statusError = $state(false);
  /** Bumped every refresh so live pages can reload. */
  tick = $state(0);

  async refresh() {
    try {
      const [days, status] = await Promise.all([insights.days(), api.status()]);
      this.days = days;
      this.status = status;
      this.statusError = false;
    } catch {
      this.statusError = true;
    }
    this.tick++;
  }

  lines = $state<NetworkLine[]>([]);
  routes = $state<Route[]>([]);
  rail = $derived(new Set(this.routes.filter((r) => r.route_type !== 3).map((r) => r.route_id)));

  /** Route shapes and the route list, loaded once for maps and pickers. */
  async loadNetwork() {
    if (this.routes.length) return;
    const [lines, routes] = await Promise.all([api.network(), api.routes()]);
    this.lines = lines;
    this.routes = routes;
  }

  get latest(): string | undefined { return this.days.at(-1)?.date; }

  /** Collector state for the header: ok / stale (> 60 s) / stopped (> 5 min). */
  get collector(): { cls: "ok" | "warn" | "bad" | "off"; label: string; stale: boolean } {
    const age = this.status?.last_ok_poll_age_s;
    if (this.statusError) return { cls: "bad", label: "Server unreachable", stale: true };
    if (age == null) return { cls: "off", label: "Collector not running", stale: true };
    if (age < 60) return { cls: "ok", label: `Collecting · polled ${age} s ago`, stale: false };
    if (age < 300) return { cls: "warn", label: `Stale · last poll ${Math.round(age / 60)} min ago`, stale: false };
    return { cls: "bad", label: `Stale · last poll ${age < 5400 ? Math.round(age / 60) + " min" : Math.round(age / 3600) + " h"} ago`, stale: true };
  }
}

export const app = new AppData();

/** Reactive async load: re-runs when `fn`'s reactive reads change; keeps the last data while reloading. */
export function load<T>(fn: () => Promise<T> | null) {
  const s = $state<{ data: T | null; error: string | null; loading: boolean }>({ data: null, error: null, loading: false });
  let seq = 0;
  $effect(() => {
    const p = fn();
    if (!p) return;
    const my = ++seq;
    s.loading = true;
    p.then((d) => { if (my === seq) { s.data = d; s.error = null; } })
      .catch((e) => { if (my === seq) s.error = String(e.message ?? e); })
      .finally(() => { if (my === seq) s.loading = false; });
  });
  return s;
}
