// Hash router: #/<page>/<id...>?<query>. The path names the thing, the query sets the scope,
// so every view is a URL (bookmarkable, shareable). Defaults are left out to keep links short.

export interface Route { page: string; parts: string[]; query: URLSearchParams }

function parse(hash: string): Route {
  const h = hash.replace(/^#/, "");
  const [path, qs = ""] = h.split("?");
  const parts = path.split("/").filter(Boolean).map(decodeURIComponent);
  return { page: parts[0] ?? "network", parts: parts.slice(1), query: new URLSearchParams(qs) };
}

/** Scope keys shared by every page (see the IA board): dates, weekdays, hours, modes. */
export const SCOPE_KEYS = ["from", "to", "dows", "h", "modes"] as const;

class Router {
  route = $state<Route>(parse(location.hash));

  constructor() {
    addEventListener("hashchange", () => (this.route = parse(location.hash)));
  }

  /** href for a page, keeping the current scope unless overridden. */
  href(path: string, query: Record<string, string | number | undefined | null> = {}, keepScope = true): string {
    const q = new URLSearchParams();
    if (keepScope) for (const k of SCOPE_KEYS) { const v = this.route.query.get(k); if (v) q.set(k, v); }
    for (const [k, v] of Object.entries(query)) {
      if (v === undefined || v === null || v === "") q.delete(k); else q.set(k, String(v));
    }
    const s = q.toString();
    return "#/" + path.replace(/^\//, "") + (s ? "?" + s : "");
  }

  go(path: string, query: Record<string, string | number | undefined | null> = {}, keepScope = true) {
    location.hash = this.href(path, query, keepScope);
  }

  /** Update query keys on the current page without adding a history entry. */
  set(query: Record<string, string | number | undefined | null>, replace = true) {
    const q = new URLSearchParams(this.route.query);
    for (const [k, v] of Object.entries(query)) {
      if (v === undefined || v === null || v === "") q.delete(k); else q.set(k, String(v));
    }
    const path = [this.route.page, ...this.route.parts].map(encodeURIComponent).join("/");
    const s = q.toString();
    const h = "#/" + path + (s ? "?" + s : "");
    if (replace) { history.replaceState(null, "", h); this.route = parse(h); }
    else location.hash = h;
  }

  get(key: string): string | null { return this.route.query.get(key); }

  scopeParams(keys: readonly string[] = SCOPE_KEYS): Record<string, string | undefined> {
    const out: Record<string, string | undefined> = {};
    for (const k of keys) out[k] = this.route.query.get(k) ?? undefined;
    return out;
  }
}

export const router = new Router();
