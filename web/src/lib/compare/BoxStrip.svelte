<script lang="ts">
  // Per slot: box p25–p75, median tick, whiskers min–max, every trip as a dot, timetable tick.
  import type { Series } from "../series";
  import { tip } from "../tip.svelte";
  import { dur, fmtClock } from "../format";
  import { lin } from "../charts/scale";
  import { durDomain, minuteTicks, q } from "./util";

  let { series }: { series: Series[] } = $props();
  let w = $state(460);
  const L = 30, R = 20, ROW = 52, T = 6, B = 20;
  const rows = $derived(series.filter((s) => s.trips.length).map((s) => {
    const d = s.trips.map((t) => t.dur).sort((a, b) => a - b);
    return { s, d, p25: q(d, 0.25), p50: q(d, 0.5), p75: q(d, 0.75) };
  }));
  const height = $derived(T + rows.length * ROW + B);
  const xdom = $derived(durDomain(rows.flatMap((r) => [r.d[0], r.d[r.d.length - 1], ...(r.s.schedMedian != null ? [r.s.schedMedian] : [])])));
  const x = $derived(lin(xdom[0], xdom[1], L, w - R));
  const yc = (i: number) => T + i * ROW + 18;
</script>

<div bind:clientWidth={w}>
  <svg class="chart" width={w} {height} role="img" aria-label="Spread of travel times per slot">
    {#each minuteTicks(xdom[0], xdom[1], Math.max(3, Math.floor(w / 80))) as v}
      <line class="gl" x1={x(v)} x2={x(v)} y1={T} y2={height - B} /><text x={x(v)} y={height - 4} text-anchor="middle">{dur(v)}</text>
    {/each}
    {#each rows as r, i (r.s.c.id)}
      {@const c = r.s.color}
      <circle cx="10" cy={yc(i)} r="9" fill={c} /><text x="10" y={yc(i) + 3.8} text-anchor="middle" style="fill: #fff; font-size: 10.5px; font-weight: 750">{r.s.letter}</text>
      <line x1={x(r.d[0])} x2={x(r.d[r.d.length - 1])} y1={yc(i)} y2={yc(i)} stroke="var(--ink-2)" />
      <rect x={x(r.p25)} y={yc(i) - 10} width={Math.max(1, x(r.p75) - x(r.p25))} height="20" rx="2" fill="var(--panel)" stroke={c} stroke-width="1.5" />
      <line x1={x(r.p50)} x2={x(r.p50)} y1={yc(i) - 10} y2={yc(i) + 10} stroke={c} stroke-width="2.5" />
      {#if r.s.schedMedian != null}<line x1={x(r.s.schedMedian)} x2={x(r.s.schedMedian)} y1={yc(i) - 14} y2={yc(i) + 14} stroke="var(--sched)" stroke-width="1.4" stroke-dasharray="3 3" />{/if}
      {#each r.s.trips as t, k}
        <circle role="presentation" cx={x(t.dur)} cy={yc(i) + 18 + (k % 3) * 3} r="2.2" fill={c} fill-opacity="0.7"
          onmouseenter={(e) => tip.show(e, `${r.s.letter} · ${t.date} ${fmtClock(t.minute)}`, [{ k: "Took", v: dur(t.dur) }, { k: "Timetable", v: dur(t.sched) },
            ...(t.vehicleId ? [{ k: "Vehicle", v: t.vehicleId }] : [])])}
          onmouseleave={() => tip.hide()} />
      {/each}
    {/each}
  </svg>
</div>
