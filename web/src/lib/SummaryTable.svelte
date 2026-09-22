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
    <h2>Travel time</h2>
    <p>Minutes from departing the first stop to arriving at the second. Observed trips match the filters above;
      scheduled figures come from the current timetable, weighted by how many days each trip runs.</p>
  </figcaption>
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th rowspan="2">Segment</th>
          <th colspan="8" class="grp">Observed</th>
          <th colspan="2" class="grp">Scheduled</th>
          <th rowspan="2" class="num" title="Median of each trip's observed minus scheduled time">vs sched.</th>
        </tr>
        <tr>
          <th class="num">Trips</th>
          <th class="num">Median</th>
          <th class="num">Mean</th>
          <th class="num" title="10th–90th percentile: the typical range">p10–p90</th>
          <th class="num" title="95th percentile: 1 trip in 20 is slower">p95</th>
          <th class="num" title="Standard deviation">Std dev</th>
          <th class="num" title="Coefficient of variation: std dev ÷ mean. Higher means less predictable.">CV</th>
          <th class="num" title="Buffer index: (p95 − median) ÷ median. Extra time to allow to arrive on time 19 times in 20.">Buffer</th>
          <th class="num">Median</th>
          <th class="num" title="Timetabled trips in a typical week matching the filters">Trips/wk</th>
        </tr>
      </thead>
      <tbody>
        {#each rows as { s, delta } (s.c.id)}
          {@const o = s.obs}
          <tr class:active={s.c.id === store.activeId} onclick={() => (store.activeId = s.c.id)}>
            <td>
              <div class="segname">
                <span class="key" style:background={s.color}></span>
                <strong>{s.letter}</strong>
                <span class="route">{s.routeShort}</span>
                <span class="stops">{s.seg.from.name} → {s.seg.to.name}</span>
              </div>
            </td>
            <td class="num">{s.trips.length.toLocaleString()}{#if s.trimmed}<span class="muted small" title="far outliers excluded"> −{s.trimmed}</span>{/if}</td>
            <td class="num strong">{fmtMin(o?.median)}</td>
            <td class="num">{fmtMin(o?.mean)}</td>
            <td class="num">{o ? `${fmtMin(o.p10)}–${fmtMin(o.p90)}` : "–"}</td>
            <td class="num">{fmtMin(o?.p95)}</td>
            <td class="num">{fmtMin(o?.std)}</td>
            <td class="num">{fmtPct(o?.cv)}</td>
            <td class="num">{fmtPct(o?.buffer)}</td>
            <td class="num">{fmtMin(s.schedMedian)}</td>
            <td class="num">{s.schedTrips.toLocaleString()}</td>
            <td class="num" class:up={delta != null && delta > 30} class:down={delta != null && delta < -30}>
              {fmtSignedMin(delta)}
            </td>
          </tr>
        {/each}
      </tbody>
    </table>
  </div>
  {#if series.some((s) => !s.trips.length)}
    <p class="small muted note">No observed trips yet for some segments. The collector records trips as they happen,
      and UTA doesn't publish realtime data at a trip's first stop.</p>
  {/if}
</figure>

<style>
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 14px 16px; margin: 0; }
  figcaption { margin-bottom: 10px; }
  figcaption p { color: var(--muted); font-size: 12px; margin-top: 2px; max-width: 90ch; }
  .table-wrap { overflow-x: auto; }
  table { border-collapse: collapse; width: 100%; font-size: 13px; }
  th, td { padding: 6px 8px; border-bottom: 1px solid var(--grid); white-space: nowrap; text-align: left; }
  th { color: var(--ink-2); font-weight: 500; font-size: 12px; }
  th.grp { text-align: center; border-bottom: 1px solid var(--axis); }
  th[title] { text-decoration: underline dotted var(--axis); text-underline-offset: 3px; cursor: help; }
  tbody tr { cursor: pointer; }
  tbody tr:hover td { background: var(--surface-2); }
  tr.active td { background: var(--surface-2); }
  .segname { display: flex; align-items: center; gap: 6px; max-width: 420px; }
  .route { font-weight: 600; }
  .stops { overflow: hidden; text-overflow: ellipsis; color: var(--ink-2); }
  .strong { font-weight: 600; }
  .up { color: var(--delta-up); }
  .down { color: var(--delta-down); }
  .note { margin-top: 8px; }
</style>
