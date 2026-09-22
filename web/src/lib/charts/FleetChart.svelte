<script lang="ts">
  import type { Gap } from "../api";
  import { tip } from "../tip.svelte";
  import { clock } from "../format";
  import { lin, hourTicks, hh, runs, d, niceMax, niceTicks } from "./scale";
  import Hatch from "../ui/Hatch.svelte";

  let { fleet, gaps, height = 180 }: { fleet: { t: number; actual: number; sched: number }[]; gaps: Gap[]; height?: number } = $props();
  let w = $state(600);
  const id = $props.id();
  const L = 40, R = 10, T = 8, B = 20;
  const t0 = $derived(fleet.length ? fleet[0].t - 300 : 0);
  const t1 = $derived(fleet.length ? fleet.at(-1)!.t + 300 : 1);
  const yt = $derived(niceTicks(Math.max(10, ...fleet.map((f) => Math.max(f.actual, f.sched)))));
  const ymax = $derived(yt.at(-1)!);
  const x = $derived(lin(t0, t1, L, w - R));
  const y = $derived(lin(0, ymax, height - B, T));
  const inGap = (t: number) => gaps.some(([a, b]) => t >= a - 300 && t <= b + 300);
  const actual = $derived(runs(fleet, (f) => f.t, (f) => !inGap(f.t) && f.actual > 0).map((r) => d(r.map((f) => [x(f.t), y(f.actual)]))));
  const sched = $derived(d(fleet.map((f) => [x(f.t), y(f.sched)])));

  function move(e: PointerEvent) {
    const r = (e.currentTarget as SVGElement).getBoundingClientRect();
    const t = t0 + ((e.clientX - r.left - L) / (w - L - R)) * (t1 - t0);
    const f = fleet.reduce((a, b) => (Math.abs(b.t - t) < Math.abs(a.t - t) ? b : a), fleet[0]);
    if (f) tip.show(e, clock(f.t), [{ k: "Observed", v: inGap(f.t) ? "no data" : String(f.actual), color: "var(--ink)" }, { k: "Timetable", v: String(f.sched), color: "var(--sched)" }]);
  }
</script>

<div bind:clientWidth={w}>
  <svg class="chart" width={w} {height} role="img" aria-label="Vehicles in service vs timetable" onpointermove={move} onpointerleave={() => tip.hide()}>
    <Hatch {id} />
    {#each yt as v}<line class="gl" x1={L} x2={w - R} y1={y(v)} y2={y(v)} /><text x={L - 6} y={y(v) + 3.5} text-anchor="end">{v}</text>{/each}
    {#each gaps as [a, b]}
      {@const xa = Math.max(L, x(a))}{@const xb = Math.min(w - R, x(b))}
      {#if xb > xa}<rect x={xa} y={T} width={xb - xa} height={height - B - T} fill="url(#{id})" />{#if xb - xa > 70}<text x={(xa + xb) / 2} y={T + 12} text-anchor="middle" style="font-weight: 500">collector offline</text>
        <text x={(xa + xb) / 2} y={T + 24} text-anchor="middle">{clock(a)}–{clock(b)}</text>{/if}{/if}
    {/each}
    {#each hourTicks(t0, t1, w < 500 ? 3 : 1) as t}<text x={x(t)} y={height - 4} text-anchor="middle">{hh(t)}</text>{/each}
    <path d={sched} fill="none" stroke="var(--sched)" stroke-width="1.6" stroke-dasharray="5 4" />
    {#each actual as p}<path d={p} fill="none" stroke="var(--ink)" stroke-width="2" stroke-linejoin="round" />{/each}
  </svg>
</div>
