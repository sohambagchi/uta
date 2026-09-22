<script lang="ts">
  // End-to-end running time per trip against the timetable, by scheduled departure.
  import type { Gap, RouteDay } from "../api";
  import { tip } from "../tip.svelte";
  import { clock, dur } from "../format";
  import { lin, hourTicks, hh } from "./scale";
  import Hatch from "../ui/Hatch.svelte";

  let { trips, gaps, color, height = 200 }: { trips: RouteDay["runtime"]["trips"]; gaps: Gap[]; color: string; height?: number } = $props();
  const id = $props.id();
  let w = $state(460);
  const L = 40, R = 18, T = 8, B = 20;
  const t0 = $derived(Math.floor((Math.min(...trips.map((t) => t.t)) - 1800) / 3600) * 3600);
  const t1 = $derived(Math.ceil((Math.max(...trips.map((t) => t.t)) + 1800) / 3600) * 3600);
  const vals = $derived(trips.flatMap((t) => [t.obs, t.sched]));
  const med = $derived.by(() => { const s = trips.map((t) => t.sched).sort((a, b) => a - b); return s[Math.floor((s.length - 1) / 2)]; });
  const v0 = $derived(Math.floor((Math.min(...vals) - 60) / 120) * 120);
  const v1 = $derived(Math.ceil((Math.max(...vals) + 60) / 120) * 120);
  const x = $derived(lin(t0, t1, L, w - R));
  const y = $derived(lin(v0, v1, height - B, T));
  const yt = $derived.by(() => {
    const span = (v1 - v0) / 60, st = span > 30 ? 10 : span > 12 ? 4 : 2;
    const out: number[] = [];
    for (let m = Math.ceil(v0 / 60 / st) * st; m * 60 <= v1; m += st) out.push(m * 60);
    return out;
  });
</script>

<div bind:clientWidth={w}>
  <svg class="chart" width={w} {height} role="img" aria-label="Running time vs timetable">
    <Hatch {id} />
    {#each yt as v}<line class="gl" x1={L} x2={w - R} y1={y(v)} y2={y(v)} /><text x={L - 6} y={y(v) + 3.5} text-anchor="end">{Math.round(v / 60)}</text>{/each}
    <text x="2" y={height - 4}>min</text>
    {#each gaps as [a, b]}
      {@const xa = Math.max(L, x(a))}{@const xb = Math.min(w - R, x(b))}
      {#if xb > xa}<rect x={xa} y={T} width={xb - xa} height={height - B - T} fill="url(#{id})" />{/if}
    {/each}
    {#each hourTicks(t0, t1, (t1 - t0) / 3600 > 10 ? 2 : 1) as t}<text x={x(t)} y={height - 4} text-anchor="middle">{hh(t)}</text>{/each}
    <line x1={L} x2={w - R} y1={y(med)} y2={y(med)} stroke="var(--sched)" stroke-width="1.5" stroke-dasharray="5 4" />
    <text x={w - R} y={y(med) - 5} text-anchor="end" style="paint-order: stroke; stroke: var(--panel); stroke-width: 3px">timetable {dur(med)}</text>
    {#each trips as t}
      <line x1={x(t.t) - 5} x2={x(t.t) + 5} y1={y(t.sched)} y2={y(t.sched)} stroke="var(--sched)" stroke-width="1.5" />
      <line x1={x(t.t)} x2={x(t.t)} y1={y(t.sched)} y2={y(t.obs)} stroke="var(--ink-2)" />
      <circle role="presentation" cx={x(t.t)} cy={y(t.obs)} r="4" fill={color}
        onmouseenter={(e) => tip.show(e, `${t.date} · ${clock(t.t)}`, [{ k: "Observed", v: dur(t.obs) }, { k: "Timetable", v: dur(t.sched) },
          { k: "Difference", v: (t.obs >= t.sched ? "+" : "−") + dur(Math.abs(t.obs - t.sched)) }])}
        onmouseleave={() => tip.hide()} />
    {/each}
  </svg>
</div>
