<script lang="ts">
  // Observed gaps between consecutive arrivals at one station against the timetable's headway.
  import type { Gap, RouteDay } from "../api";
  import { tip } from "../tip.svelte";
  import { clock, dur } from "../format";
  import { lin, hourTicks, hh, niceMax } from "./scale";
  import Hatch from "../ui/Hatch.svelte";

  let { hw, gaps, height = 190 }: { hw: NonNullable<RouteDay["headways"]>; gaps: Gap[]; height?: number } = $props();
  const id = $props.id();
  let w = $state(700);
  const L = 40, R = 8, T = 8, B = 20;
  const sched = $derived(hw.sched.map((s) => s.t));
  const t0 = $derived(Math.min(...sched, ...hw.obs.map((o) => o.t - o.h)) - 600);
  const t1 = $derived(Math.max(...sched, ...hw.obs.map((o) => o.t)) + 600);
  // scheduled headway as steps; a step across a collector gap is not a real headway
  const steps = $derived.by(() => {
    const all = sched.slice(1).map((t, k) => ({ a: sched[k], b: t, h: t - sched[k] })).filter((s) => s.h > 0);
    const med = [...all].map((s) => s.h).sort((p, q) => p - q)[Math.floor(all.length / 2)] ?? 0;
    return all.filter((s) => s.h <= 3 * med && !gaps.some(([g0, g1]) => s.a < g1 && s.b > g0));
  });
  // a gap spanning a collector outage is as unknown as one spanning an unseen arrival
  const obs = $derived(hw.obs.map((o) => ({ ...o, excluded: o.spans_missing || gaps.some(([g0, g1]) => o.t - o.h < g1 && o.t > g0) })));
  const ymax = $derived(niceMax(Math.max(600, ...obs.filter((o) => !o.excluded).map((o) => o.h), ...steps.map((s) => s.h * 1.5)) * 1.1 / 60) * 60);
  const x = $derived(lin(t0, t1, L, w - R));
  const y = $derived(lin(0, ymax, height - B, T));
  // ticks at whole, round minutes
  const yt = $derived.by(() => {
    const stepM = niceMax(ymax / 60 / 4, [1, 2, 5, 10]);
    const out: number[] = [];
    for (let m = 0; m * 60 <= ymax; m += stepM) out.push(m * 60);
    return out;
  });
  // gaps taller than the axis (spanning unseen arrivals) are pinned to the top
  const shown = $derived(obs.map((o) => ({ ...o, yh: Math.min(o.h, ymax), above: o.h > ymax })));
</script>

<div bind:clientWidth={w}>
  {#if hw.obs.length}
    <svg class="chart" width={w} {height} role="img" aria-label="Headways">
      <Hatch {id} />
      {#each yt as v}<line class="gl" x1={L} x2={w - R} y1={y(v)} y2={y(v)} /><text x={L - 6} y={y(v) + 3.5} text-anchor="end">{Math.round(v / 60)}</text>{/each}
      <text x="2" y={height - 4}>min</text>
      {#each gaps as [a, b]}
        {@const xa = Math.max(L, x(a))}{@const xb = Math.min(w - R, x(b))}
        {#if xb > xa}<rect x={xa} y={T} width={xb - xa} height={height - B - T} fill="url(#{id})" />{/if}
      {/each}
      {#each steps as s}
        <rect x={x(s.a)} y={y(s.h * 1.5)} width={Math.max(0, x(s.b) - x(s.a))} height={Math.max(0, y(s.h * 0.25) - y(s.h * 1.5))} fill="var(--sunk)" />
      {/each}
      {#each steps as s}<line x1={x(s.a)} x2={x(s.b)} y1={y(s.h)} y2={y(s.h)} stroke="var(--sched)" stroke-width="1.4" stroke-dasharray="4 3" />{/each}
      {#each hourTicks(t0, t1, (t1 - t0) / 3600 > 12 ? 2 : 1) as t}<text x={x(t)} y={height - 4} text-anchor="middle">{hh(t)}</text>{/each}
      {#each hw.sched.filter((s) => !s.observed) as s}<line x1={x(s.t)} x2={x(s.t)} y1={height - B - 6} y2={height - B} stroke="var(--late-3)" stroke-width="2" />{/each}
      {#each shown as o}
        {@const c = o.excluded ? "var(--faint)" : "var(--ink)"}
        <line x1={x(o.t)} x2={x(o.t)} y1={y(0)} y2={y(o.yh)} stroke={c} opacity="0.5" />
        <circle role="presentation" cx={x(o.t)} cy={y(o.yh)} r="3.4" fill={o.excluded ? "var(--panel)" : c} stroke={c} stroke-width="1.5"
          onmouseenter={(e) => tip.show(e, clock(o.t), [{ k: "Gap to previous", v: dur(o.h) }, { k: "Scheduled", v: dur(o.s) },
            ...(o.above ? [{ k: "Plotted", v: "above axis" }] : []),
            ...(o.excluded ? [{ k: "Excluded", v: o.spans_missing ? "spans an unseen arrival" : "spans a collector gap" }] : [])])}
          onmouseleave={() => tip.hide()} />
        {#if o.above}<path d="M{x(o.t) - 4},{y(o.yh) - 6}L{x(o.t) + 4},{y(o.yh) - 6}L{x(o.t)},{y(o.yh) - 12}Z" fill={c} pointer-events="none" />{/if}
      {/each}
    </svg>
  {:else}
    <div class="none">No consecutive observed arrivals here.</div>
  {/if}
</div>

<style>
  .none { color: var(--muted); font-size: 12.5px; padding: 30px; text-align: center; background: var(--panel-2); border-radius: 4px; }
</style>
