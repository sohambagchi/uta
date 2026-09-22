<script lang="ts">
  // GPS trace without a basemap: faint route shapes for context, pings coloured by speed (a trip) or by
  // trip (a vehicle's day), stop circles with a few labels that stay inside the box.
  import type { NetworkLine, TripStop } from "../api";
  import { clock } from "../format";
  import { tip } from "../tip.svelte";

  type Ping = [number, number, number, number | null, (string | null)?];
  let { gps, stops = [], context = [], colorBy = "speed", height = 330 }: {
    gps: Ping[]; stops?: TripStop[]; context?: NetworkLine[]; colorBy?: "speed" | "trip"; height?: number;
  } = $props();
  let w = $state(420);
  const sp = (v: number | null) => (v == null ? "var(--faint)" : v < 3 ? "var(--late-3)" : v < 10 ? "var(--late-1)" : v < 18 ? "var(--ink-2)" : "var(--early)");
  const ss = $derived(stops.filter((s) => s.lat != null && s.lon != null));
  // trips alternate between two ink tones in the order they ran; pings between trips are faint
  const tripOrder = $derived([...new Set(gps.map((p) => p[4]).filter((t): t is string => !!t))]);
  const tc = (t: string | null | undefined) => (!t ? "var(--faint)" : tripOrder.indexOf(t) % 2 ? "var(--sched)" : "var(--ink)");
  const box = $derived.by(() => {
    const lats = [...gps.map((p) => p[1]), ...ss.map((s) => s.lat!)], lons = [...gps.map((p) => p[2]), ...ss.map((s) => s.lon!)];
    if (!lats.length) return null;
    const la0 = Math.min(...lats) - 0.004, la1 = Math.max(...lats) + 0.004, lo0 = Math.min(...lons) - 0.006, lo1 = Math.max(...lons) + 0.006;
    const kx = Math.cos(((la0 + la1) / 2) * Math.PI / 180);
    const k = Math.min((w - 20) / ((lo1 - lo0) * kx), (height - 20) / (la1 - la0));
    const ox = (w - (lo1 - lo0) * kx * k) / 2, oy = (height - (la1 - la0) * k) / 2;
    // the visible area in lat/lon (wider than the data when the box's aspect differs)
    const vla0 = la1 - height / k + oy / k, vla1 = la1 + oy / k, vlo0 = lo0 - ox / (kx * k), vlo1 = lo0 + (w - ox) / (kx * k);
    return { P: (lat: number, lon: number): [number, number] => [ox + (lon - lo0) * kx * k, oy + (la1 - lat) * k], vla0, vla1, vlo0, vlo1 };
  });
  const ctx = $derived.by(() => {
    if (!box || !context.length) return [];
    const m = 0.02;
    return context.map((l) => {
      const pts = l.coords.filter(([lo, la]) => la >= box.vla0 - m && la <= box.vla1 + m && lo >= box.vlo0 - m && lo <= box.vlo1 + m);
      return pts.length > 1 ? "M" + pts.map(([lo, la]) => box.P(la, lo).map((v) => v.toFixed(1)).join(",")).join("L") : "";
    }).filter(Boolean);
  });
  const segs = $derived(box ? gps.slice(1).map((p, i) => {
    const q = gps[i];
    return { a: box.P(q[1], q[2]), b: box.P(p[1], p[2]), c: colorBy === "trip" ? tc(p[4] ?? null) : sp(p[3]), p };
  }) : []);
  const labelled = $derived(new Set([0, ss.length - 1, Math.floor(ss.length / 3), Math.floor((2 * ss.length) / 3)]));
  const LABEL_PX = 6.2;   // ~ px per character at 10.5 px
  /** Label placement that stays inside the box: right of the stop, or left when it would overrun. */
  function place(x: number, text: string): { x: number; anchor: "start" | "end" } {
    const wid = text.length * LABEL_PX;
    if (x + 7 + wid <= w - 4) return { x: x + 7, anchor: "start" };
    if (x - 7 - wid >= 4) return { x: x - 7, anchor: "end" };
    return x > w / 2 ? { x: w - 4, anchor: "end" } : { x: 4, anchor: "start" };
  }
  function hover(e: MouseEvent, p: Ping) {
    tip.show(e, clock(p[0], true), [
      ...(p[4] ? [{ k: "Trip", v: String(p[4]) }] : colorBy === "trip" ? [{ k: "Trip", v: "between trips" }] : []),
      { k: "Speed", v: p[3] == null ? "—" : `${p[3].toFixed(1)} m/s` },
    ]);
  }
</script>

<div bind:clientWidth={w}>
  <svg class="chart" width={w} {height} role="img" aria-label="GPS trace" style="background: var(--panel-2); border-radius: 4px; overflow: hidden">
    {#if box}
      {#each ctx as d}<path {d} fill="none" stroke="var(--grid)" stroke-width="1.5" stroke-linejoin="round" />{/each}
      {#each segs as s}<line x1={s.a[0]} y1={s.a[1]} x2={s.b[0]} y2={s.b[1]} stroke={s.c} stroke-width="3" stroke-linecap="round" />{/each}
      {#each segs as s}
        <line role="presentation" x1={s.a[0]} y1={s.a[1]} x2={s.b[0]} y2={s.b[1]} stroke="transparent" stroke-width="10"
          onmouseenter={(e) => hover(e, s.p)} onmousemove={(e) => hover(e, s.p)} onmouseleave={() => tip.hide()} />
      {/each}
      {#each ss as s, i}
        {@const p = box.P(s.lat!, s.lon!)}
        <circle role="presentation" cx={p[0]} cy={p[1]} r="3" fill="var(--panel)" stroke={s.observed ? "var(--ink)" : "var(--faint)"} stroke-width="1.3"
          onmouseenter={(e) => tip.show(e, s.name ?? "", [{ k: "Arrived", v: clock(s.obs, true) }])} onmouseleave={() => tip.hide()} />
        {#if labelled.has(i)}
          {@const t = (s.name ?? "").replace(/ Station$/, "")}
          {@const at = place(p[0], t)}
          <text x={at.x} y={p[1] + 4} text-anchor={at.anchor} style="fill: var(--ink); font-size: 10.5px; font-weight: 600; paint-order: stroke; stroke: var(--panel-2); stroke-width: 3px">{t}</text>
        {/if}
      {/each}
    {:else}
      <text x={w / 2} y={height / 2} text-anchor="middle">No GPS</text>
    {/if}
  </svg>
</div>
