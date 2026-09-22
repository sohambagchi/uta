<script lang="ts">
  import type { VehicleView, Gap } from "../api";
  import { dcol, delay, clock } from "../format";
  import { tip } from "../tip.svelte";
  import { router } from "../router.svelte";
  import { lin, hourTicks, hh } from "./scale";
  import Hatch from "../ui/Hatch.svelte";
  let { trips, gaps, date, height = 210 }: { trips: VehicleView["trips"]; gaps: Gap[]; date: string; height?: number } = $props();
  let w = $state(1300);
  const id = $props.id();
  const L = 80, R = 10, T = 20, B = 24;
  const ys = 66, yo = 118;
  const times = $derived(trips.flatMap((t) => [t.sched_start, t.sched_end, t.obs_start, t.obs_end]).filter((v): v is number => v != null));
  const t0 = $derived(times.length ? Math.floor((Math.min(...times) - 900) / 1800) * 1800 : 0);
  const t1 = $derived(times.length ? Math.ceil((Math.max(...times) + 900) / 1800) * 1800 : 3600);
  const x = $derived(lin(t0, t1, L, w - R));
  const lbl = (t: VehicleView["trips"][0], width: number) => {
    const s = `${t.short ?? ""} → ${(t.head ?? "").replace(/ Station$/, "")}`;
    const room = Math.floor((width - 10) / 6);
    return room < 3 ? "" : s.length <= room ? s : s.slice(0, Math.max(2, room - 1)) + "…";
  };
  // layover between consecutive scheduled trips: "layover 17 min", "17m" when tight, below the lane when tighter
  const layovers = $derived(trips.slice(0, -1).map((t, k) => {
    const n = trips[k + 1];
    if (t.sched_end == null || n.sched_start == null || n.sched_start <= t.sched_end) return null;
    const a = x(t.sched_end), b = x(n.sched_start), m = Math.round((n.sched_start - t.sched_end) / 60);
    const room = b - a;
    return room >= 84 ? { x: (a + b) / 2, y: ys + 30, s: `layover ${m} min` }
      : room >= 24 ? { x: (a + b) / 2, y: ys + 30, s: `${m}m` }
      : { x: (a + b) / 2, y: ys - 20, s: `${m}m` };
  }));
  // end-delay labels under the observed bars, dropped only when they would collide with the previous one
  const endLabels = $derived.by(() => {
    const out: { x: number; s: string }[] = [];
    let last = -Infinity;
    for (const t of trips) {
      if (t.obs_start == null || t.obs_end == null) continue;
      const a = x(t.obs_start), b = Math.max(x(t.obs_end), a + 3), s = delay(t.d_last);
      const half = (s.length * 6.2) / 2;
      if (b - half < last + 6) continue;          // the tooltip still carries it
      out.push({ x: b, s });
      last = b + half;
    }
    return out;
  });
</script>

<div bind:clientWidth={w}>
  <svg class="chart" width={w} {height} role="img" aria-label="Vehicle timeline">
    <Hatch {id} />
    {#each hourTicks(t0, t1, w < 700 ? 2 : 1) as t}<line class="gl" x1={x(t)} x2={x(t)} y1={T} y2={height - B} /><text x={x(t)} y={height - 6} text-anchor="middle">{hh(t)}</text>{/each}
    {#each gaps as [a, b]}
      {@const xa = Math.max(L, x(a))}{@const xb = Math.min(w - R, x(b))}
      {#if xb > xa}<rect x={xa} y={T} width={xb - xa} height={height - B - T} fill="url(#{id})" /><text x={(xa + xb) / 2} y={T + 11} text-anchor="middle">{clock(a)}–{clock(b)}</text>{/if}
    {/each}
    <text x="0" y={ys + 4} style="font-weight: 650; letter-spacing: .05em">TIMETABLE</text>
    <text x="0" y={yo + 4} style="font-weight: 650; letter-spacing: .05em">OBSERVED</text>
    {#each trips as t, k}
      {#if t.sched_start != null && t.sched_end != null}
        {@const a = x(t.sched_start)}{@const b = x(t.sched_end)}
        <rect x={a} y={ys - 14} width={Math.max(2, b - a)} height="28" rx="3" fill="var(--panel)" stroke="var(--sched)" stroke-width="1.2" stroke-dasharray="4 3" />
        <text x={a + 6} y={ys + 4} style="fill: var(--ink-2); font-size: 10.5px; font-weight: 550">{lbl(t, b - a)}</text>
      {/if}
      {#if t.obs_start != null && t.obs_end != null}
        {@const a = x(t.obs_start)}{@const b = Math.max(x(t.obs_end), a + 3)}
        <a href={router.href(`trip/${t.trip_id}`, { date })} aria-label="Trip {t.trip_id}">
          <rect role="presentation" x={a} y={yo - 14} width={b - a} height="28" rx="3" fill="var(--ink)"
            onmouseenter={(e) => tip.show(e, `${t.short} → ${t.head ?? ""}`, [{ k: "Trip", v: t.trip_id }, { k: "Scheduled", v: `${clock(t.sched_start)}–${clock(t.sched_end)}` }, { k: "Start delay", v: delay(t.d_first) }, { k: "End delay", v: delay(t.d_last) }, { k: "Stops seen", v: String(t.n) }])}
            onmouseleave={() => tip.hide()} />
        </a>
        {#if b - a > 40}<text x={a + 10} y={yo + 4} pointer-events="none" style="fill: var(--panel); font-size: 11px; font-weight: 700">{t.short}</text>{/if}
        <circle cx={a} cy={yo} r="5" fill={dcol(t.d_first)} stroke="var(--panel)" stroke-width="1.5" pointer-events="none" />
        <circle cx={b} cy={yo} r="5" fill={dcol(t.d_last)} stroke="var(--panel)" stroke-width="1.5" pointer-events="none" />
      {/if}
    {/each}
    {#each layovers as l}{#if l}<text x={l.x} y={l.y} text-anchor="middle">{l.s}</text>{/if}{/each}
    {#each endLabels as l}<text x={l.x} y={yo + 28} text-anchor="middle" style="fill: var(--ink-2); font-weight: 600">{l.s}</text>{/each}
  </svg>
</div>
