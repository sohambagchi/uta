<script lang="ts">
  // Connection slack (next departure minus arrival) by time of day: timetable vs observed.
  import type { StationView } from "../api";
  import { clock, dur } from "../format";
  import { tip } from "../tip.svelte";
  import { lin, hourTicks, hh } from "./scale";

  type Ev = NonNullable<StationView["xfer"]>["events"][number];
  let { events, walk = 180, color = "var(--ink)", height = 170 }: { events: Ev[]; walk?: number; color?: string; height?: number } = $props();
  let w = $state(520);
  const L = 34, R = 8, T = 8, B = 18;
  const t0 = $derived(Math.min(...events.map((e) => e.arr_sched)) - 1800);
  const t1 = $derived(Math.max(...events.map((e) => e.arr_sched)) + 1800);
  const ymax = $derived(Math.max(15 * 60, ...events.map((e) => Math.max(e.slack_sched, e.slack_obs ?? 0))) + 60);
  const x = $derived(lin(t0, t1, L, w - R));
  const y = $derived(lin(Math.min(0, ...events.map((e) => e.slack_obs ?? 0)), ymax, height - B, T));
  const yt = $derived([0, 5, 10, 15, 20, 25, 30].filter((m) => m * 60 <= ymax));
  const made = (e: Ev) => e.slack_obs != null && e.slack_obs >= walk;
</script>

<div bind:clientWidth={w}>
  <svg class="chart" width={w} {height} role="img" aria-label="Transfer slack by time of day">
    {#each yt as m}<line class="gl" x1={L} x2={w - R} y1={y(m * 60)} y2={y(m * 60)} /><text x={L - 6} y={y(m * 60) + 3.5} text-anchor="end">{m}</text>{/each}
    <text x="0" y={height - 4}>min</text>
    <line x1={L} x2={w - R} y1={y(walk)} y2={y(walk)} stroke="var(--late-3)" stroke-dasharray="3 3" />
    <text x={L + 4} y={y(walk) - 4} style="fill: var(--late-3); paint-order: stroke; stroke: var(--panel); stroke-width: 3px">walk {dur(walk)}</text>
    {#each hourTicks(t0, t1, w < 500 ? 4 : 2) as t}<text x={x(t)} y={height - 4} text-anchor="middle">{hh(t)}</text>{/each}
    {#each events as e}
      <line x1={x(e.arr_sched) - 4} x2={x(e.arr_sched) + 4} y1={y(e.slack_sched)} y2={y(e.slack_sched)} stroke="var(--sched)" stroke-width="2" />
      {#if e.slack_obs != null}
        <line x1={x(e.arr_sched)} x2={x(e.arr_sched)} y1={y(e.slack_sched)} y2={y(e.slack_obs)} stroke="var(--axis)" />
        <circle role="presentation" cx={x(e.arr_sched)} cy={y(e.slack_obs)} r="4.5" fill={made(e) ? color : "var(--late-3)"} stroke="var(--panel)"
          onmouseenter={(ev) => tip.show(ev, `Arrival ${clock(e.arr_sched)}`, [
            { k: "Arrived", v: clock(e.arr_obs, true) }, { k: "Departed", v: clock(e.dep_obs, true) },
            { k: "Slack", v: dur(e.slack_obs) }, { k: "Timetable", v: dur(e.slack_sched) }, { k: "Connection", v: made(e) ? "made" : "missed" }])}
          onmouseleave={() => tip.hide()} />
      {:else}
        <line x1={x(e.arr_sched)} x2={x(e.arr_sched)} y1={height - B - 6} y2={height - B} stroke="var(--faint)" stroke-width="1.5" />
      {/if}
    {/each}
  </svg>
</div>
