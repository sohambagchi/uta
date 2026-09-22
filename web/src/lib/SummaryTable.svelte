<script lang="ts">
  import type { Series } from "./series";
  import { store } from "./store.svelte";
  import { vsSchedule } from "./stats";
  import { fmtMin, fmtPct, fmtSignedMin } from "./format";

  let { series }: { series: Series[] } = $props();

  const rows = $derived(series.map((s) => ({ s, delta: vsSchedule(s.trips) })));
</script>

<figure class="card">
  <figcaption>
    <h2>Travel time at a glance</h2>
    <p>Minutes from leaving the first stop to arriving at the second. Measured rides match the filters above;
      timetable figures come from the current schedule, weighted by how many days each trip runs.</p>
  </figcaption>
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th rowspan="2">Ride</th>
          <th colspan="8" class="grp">Measured</th>
          <th colspan="2" class="grp">Timetable</th>
          <th rowspan="2" class="num" title="Median of each ride's measured minus timetabled time">vs timetable</th>
        </tr>
        <tr>
          <th class="num">Rides</th>
          <th class="num" title="Median: half of rides are faster">Typical</th>
          <th class="num">Mean</th>
          <th class="num" title="10th–90th percentile: the typical range">p10–p90</th>
          <th class="num" title="95th percentile: 1 trip in 20 is slower">p95</th>
          <th class="num" title="Standard deviation">Std dev</th>
          <th class="num" title="Coefficient of variation: std dev ÷ mean. Higher means less predictable.">CV</th>
          <th class="num" title="Buffer index: (p95 − median) ÷ median. Extra time to allow to arrive on time 19 times in 20.">Buffer</th>
          <th class="num" title="Median">Typical</th>
          <th class="num" title="Timetabled trips in a typical week matching the filters">Trips/wk</th>
        </tr>
      </thead>
      <tbody>
        {#each rows as { s, delta } (s.c.id)}
          {@const o = s.obs}
          <tr class:active={s.c.id === store.activeId} onclick={() => (store.activeId = s.c.id)}>
            <td>
              <div class="segname">
                <span class="bullet" style:--c={s.color}>{s.letter}</span>
                <span class="route">{s.routeShort}</span>
                <span class="stops">{s.seg.from.name} → {s.seg.to.name}</span>
              </div>
            </td>
            <td class="num">{s.trips.length.toLocaleString()}{#if s.trimmed}<span class="muted small" title="far outliers excluded"> −{s.trimmed}</span>{/if}</td>
            <td class="num strong">{fmtMin(o?.median)}{#if o}<span class="unit"> min</span>{/if}</td>
            <td class="num">{fmtMin(o?.mean)}</td>
            <td class="num">{o ? `${fmtMin(o.p10)}–${fmtMin(o.p90)}` : "–"}</td>
            <td class="num">{fmtMin(o?.p95)}</td>
            <td class="num">{fmtMin(o?.std)}</td>
            <td class="num">{fmtPct(o?.cv)}</td>
            <td class="num">{fmtPct(o?.buffer)}</td>
            <td class="num">{fmtMin(s.schedMedian)}</td>
            <td class="num">{s.schedTrips.toLocaleString()}</td>
            <td class="num">
              <span class="delta" class:up={delta != null && delta > 30} class:down={delta != null && delta < -30}>{fmtSignedMin(delta)}</span>
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
  {#if series.some((s) => !s.trips.length)}
    <p class="small muted note">No measured rides yet for some of these. The collector records trips as they happen,
      and UTA doesn't publish live data at a trip's first stop.</p>
  {/if}
</figure>

<style>
  .table-wrap { overflow-x: auto; margin: 0 -8px; }
  table { border-collapse: separate; border-spacing: 0; width: 100%; font-size: 14px; }
  th, td { padding: 9px 8px; border-bottom: 1px solid var(--grid); white-space: nowrap; text-align: left; }
  th { color: var(--muted); font-weight: 600; font-size: 12px; }
  th.grp { text-align: center; border-bottom: 2px solid var(--axis); color: var(--ink-2); text-transform: uppercase;
    letter-spacing: .05em; font-size: 11px; }
  th[title] { text-decoration: underline dotted var(--axis); text-underline-offset: 3px; cursor: help; }
  tbody tr { cursor: pointer; }
  tbody tr:last-child td { border-bottom: 0; }
  tbody tr:hover td { background: var(--surface-2); }
  tr.active td { background: var(--surface-2); }
  tr td:first-child { border-radius: 10px 0 0 10px; }
  tr td:last-child { border-radius: 0 10px 10px 0; }
  .segname { display: flex; align-items: center; gap: 8px; max-width: 440px; }
  .route { font-weight: 700; }
  .stops { overflow: hidden; text-overflow: ellipsis; color: var(--ink-2); }
  .strong { font-weight: 700; font-size: 16px; }
  .unit { font-size: 12px; font-weight: 500; color: var(--muted); }
  .delta { display: inline-block; padding: 1px 8px; border-radius: 999px; font-weight: 600; }
  .up { color: var(--delta-up); background: color-mix(in srgb, var(--delta-up) 11%, transparent); }
  .down { color: var(--delta-down); background: color-mix(in srgb, var(--delta-down) 11%, transparent); }
  .note { margin-top: 10px; }
</style>
