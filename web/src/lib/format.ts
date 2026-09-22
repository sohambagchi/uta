export const DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
export const LETTERS = ["A", "B", "C", "D"];
export const MODE_NAMES: Record<number, string> = { 0: "TRAX & streetcar", 1: "Subway", 2: "FrontRunner", 3: "Bus" };
export const TZ = "America/Denver";

/** Seconds -> minutes with one decimal under 10, whole minutes above. */
export function fmtMin(sec: number | null | undefined): string {
  if (sec == null || !isFinite(sec)) return "–";
  const m = sec / 60;
  return Math.abs(m) < 10 ? m.toFixed(1) : Math.round(m).toString();
}
export function fmtSignedMin(sec: number | null | undefined): string {
  if (sec == null || !isFinite(sec)) return "–";
  const s = fmtMin(Math.abs(sec));
  if (/^0(\.0)?$/.test(s)) return s;   // no signed zero
  return sec > 0 ? `+${s}` : sec < 0 ? `−${s}` : s;
}
export function fmtPct(v: number | null | undefined, digits = 0): string {
  return v == null || !isFinite(v) ? "–" : (v * 100).toFixed(digits) + "%";
}
/** 24-hour labels, like every other time in the app. */
export function fmtHour(h: number): string {
  return String(((Math.round(h) % 24) + 24) % 24).padStart(2, "0");
}
export function fmtClock(minute: number): string {
  const h = Math.floor(minute / 60) % 24, m = Math.floor(minute % 60);
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}
/** Today's service date in Salt Lake minus n-1 days (n=1 -> today). */
export function denverDaysAgo(n: number): string {
  const d = new Date(Date.now() - (n - 1) * 86400_000);
  return new Intl.DateTimeFormat("en-CA", { timeZone: TZ }).format(d);
}
export function routeLabel(r: { route_short_name: string; route_long_name: string } | undefined): string {
  if (!r) return "";
  const long = r.route_long_name ? titleCase(r.route_long_name) : "";
  return long ? `${r.route_short_name} · ${long}` : r.route_short_name;
}
function titleCase(s: string): string {
  return s === s.toUpperCase() ? s.toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase()) : s;
}

// ---------------------------------------------------------------- dashboard formats
// Delays are signed m:ss (+2:10 late, −0:45 early); durations m:ss or h:mm:ss; clock times are
// service-day HH:MM (25:10 stays 25:10). U+2212 for minus.

export const MINUS = "−";

export function delay(s: number | null | undefined, zero = "0:00"): string {
  if (s == null || !isFinite(s)) return "—";
  const r = Math.round(s);
  if (r === 0) return zero;
  const a = Math.abs(r);
  return `${r > 0 ? "+" : MINUS}${Math.floor(a / 60)}:${String(a % 60).padStart(2, "0")}`;
}
export function dur(s: number | null | undefined): string {
  if (s == null || !isFinite(s)) return "—";
  const r = Math.round(s);
  if (r >= 3600) return `${Math.floor(r / 3600)}:${String(Math.floor((r % 3600) / 60)).padStart(2, "0")}:${String(r % 60).padStart(2, "0")}`;
  return `${Math.floor(r / 60)}:${String(r % 60).padStart(2, "0")}`;
}
export function clock(s: number | null | undefined, secs = false): string {
  if (s == null || !isFinite(s)) return "—";
  const r = Math.round(s);
  const h = Math.floor(r / 3600), m = Math.floor((r % 3600) / 60);
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}` + (secs ? `:${String(r % 60).padStart(2, "0")}` : "");
}
export function pct(v: number | null | undefined, d = 1): string {
  return v == null || !isFinite(v) ? "—" : (v * 100).toFixed(d) + "%";
}
export function n(v: number | null | undefined): string {
  return v == null ? "—" : v.toLocaleString("en-US");
}
export function epochClock(ts: number | null | undefined, secs = true): string {
  if (ts == null) return "—";
  return new Intl.DateTimeFormat("en-GB", { timeZone: TZ, hour: "2-digit", minute: "2-digit", second: secs ? "2-digit" : undefined })
    .format(new Date(ts * 1000));
}
export function dateLabel(d: string): string {
  return new Date(d + "T12:00").toLocaleDateString("en-US", { weekday: "short", day: "numeric", month: "short", year: "numeric" });
}
export function title(s: string | null | undefined): string {
  if (!s) return "";
  return s === s.toUpperCase() ? s.toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase()) : s;
}
export const MODE_LABEL: Record<string, string> = { bus: "Bus", lrt: "Light rail", streetcar: "Streetcar", rail: "FrontRunner" };

/** Diverging delay colour: early (blue) | on time (grey) | late ramp (amber → oxblood). */
export function dcol(s: number | null | undefined): string {
  if (s == null) return "var(--faint)";
  if (s < -60) return "var(--early)";
  if (s <= 60) return "var(--ontime)";
  if (s <= 180) return "var(--late-1)";
  if (s <= 300) return "var(--late-2)";
  if (s <= 600) return "var(--late-3)";
  return "var(--late-4)";
}
/** Text colour legible on dcol(s). */
export function dink(s: number | null | undefined): string {
  if (s == null) return "var(--ink)";
  return s < -60 || s > 300 ? "#ffffff" : "#16171a";
}
export const DELAY_BINS: [string, string][] = [
  ["var(--early)", "< −1:00"], ["var(--ontime)", "±1:00"], ["var(--late-1)", "+1–3"],
  ["var(--late-2)", "+3–5"], ["var(--late-3)", "+5–10"], ["var(--late-4)", "> +10"],
];
const LINE_VARS = new Set(["701", "703", "704", "720", "750"]);
/** UTA line colour for a route (lifted in dark mode for rail lines). */
export function lineColor(short: string | null | undefined, hex: string | null | undefined): string {
  if (short && LINE_VARS.has(short)) return `var(--line-${short})`;
  return hex ? "#" + hex.replace(/^#/, "") : "var(--ink)";
}
