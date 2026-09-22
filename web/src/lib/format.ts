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
  return sec > 0 ? `+${s}` : sec < 0 ? `−${s}` : s;
}
export function fmtPct(v: number | null | undefined, digits = 0): string {
  return v == null || !isFinite(v) ? "–" : (v * 100).toFixed(digits) + "%";
}
export function fmtHour(h: number): string {
  h = ((h % 24) + 24) % 24;
  return h === 0 ? "12a" : h < 12 ? `${h}a` : h === 12 ? "12p" : `${h - 12}p`;
}
export function fmtClock(minute: number): string {
  const h = Math.floor(minute / 60) % 24, m = Math.floor(minute % 60);
  return `${fmtHour(h).replace(/[ap]$/, "")}:${String(m).padStart(2, "0")}${h < 12 ? "a" : "p"}`;
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
