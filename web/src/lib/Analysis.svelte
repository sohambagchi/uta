<script lang="ts">
  import { store } from "./store.svelte";
  import { buildSeries, type Series } from "./series";
  import Filters from "./Filters.svelte";
  import SummaryTable from "./SummaryTable.svelte";
  import Charts from "./Charts.svelte";
  import TripsTable from "./TripsTable.svelte";

  const series = $derived.by(() => {
    const out: Series[] = [];
    for (const c of store.comparisons) {
      const data = store.segmentData(c);
      if (!data || !(c.from && c.to)) continue;
      const r = store.routeById.get(data.route_id);
      out.push(buildSeries(c, data, r?.route_short_name ?? data.route_id, store.filters));
    }
    return out;
  });
  const loading = $derived(store.comparisons.some((c) => store.segment(c)?.status === "loading"));
  const pending = $derived(store.comparisons.filter((c) => c.routeId && !(c.from && c.to)).length);
  const activeSeries = $derived(series.find((s) => s.c.id === store.activeId) ?? series[0]);
</script>

<div class="analysis">
  <Filters />

  {#if !series.length}
    <div class="card empty">
      {#if loading}
        <p class="muted">Loading trips…</p>
      {:else}
        <h2>Let's time a ride</h2>
        <ol class="steps">
          <li><span class="bullet lg" style:--c="var(--series-1)">1</span>
            <div><strong>Choose a line</strong><p>Any bus, TRAX, streetcar or FrontRunner route, on the left.</p></div></li>
          <li><span class="bullet lg" style:--c="var(--series-2)">2</span>
            <div><strong>Tap two stops</strong><p>Where you'd get on and where you'd get off. Stops on the map work too.</p></div></li>
          <li><span class="bullet lg" style:--c="var(--series-3)">3</span>
            <div><strong>See how long it really takes</strong><p>Measured trip times next to the timetable, by hour and by day.</p></div></li>
        </ol>
        <p class="muted small">Add up to four rides to compare different lines over the same stops, or different stretches of
          one line. Measured times come from UTA's live feed and cover the time the collector has been running.</p>
      {/if}
    </div>
  {:else}
    <div class="legend" class:loading aria-label="Comparisons">
      {#each series as s (s.c.id)}
        <button class="item" class:active={s.c.id === store.activeId} onclick={() => (store.activeId = s.c.id)}
          style:--c={s.color} aria-pressed={s.c.id === store.activeId}>
          <span class="bullet">{s.letter}</span>
          <span class="route">{s.routeShort}</span>
          <span class="label">{s.seg.from.name} → {s.seg.to.name}</span>
        </button>
      {/each}
      {#if pending}<span class="muted small">{pending} more ride{pending > 1 ? "s" : ""} still need{pending > 1 ? "" : "s"} stops</span>{/if}
    </div>

    <div class="stack" class:loading>
      <SummaryTable {series} />
      <Charts {series} active={activeSeries} bin={store.filters.bin} />
      {#if activeSeries}<TripsTable s={activeSeries} />{/if}
    </div>
  {/if}
</div>

<style>
  .analysis { padding: 20px 24px 56px; display: grid; grid-template-columns: minmax(0, 1fr); gap: 16px; max-width: 1600px; }
  .stack { display: grid; grid-template-columns: minmax(0, 1fr); gap: 16px; }
  .empty { max-width: 760px; display: grid; gap: 18px; padding: 24px 26px; }
  .empty h2 { font-size: 20px; }
  .steps { list-style: none; margin: 0; padding: 0; display: grid; gap: 14px; }
  .steps li { display: flex; gap: 14px; align-items: flex-start; }
  .steps strong { font-size: 15px; }
  .steps p { color: var(--ink-2); font-size: 13.5px; }
  .legend { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
  .item { display: inline-flex; align-items: center; gap: 8px; border: 1.5px solid var(--border); background: var(--surface);
    border-radius: 999px; padding: 4px 14px 4px 4px; font-size: 13.5px; color: var(--ink-2); max-width: 100%;
    transition: border-color .15s, box-shadow .15s; }
  .item:hover { border-color: var(--border-strong); }
  .item.active { border-color: var(--c); color: var(--ink); box-shadow: 0 0 0 3px color-mix(in srgb, var(--c) 16%, transparent); }
  .item .route { font-weight: 700; color: var(--ink); }
  .item .label { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .loading { opacity: .5; transition: opacity .15s; }
  @media (max-width: 900px) { .analysis { padding: 16px 16px 48px; } }
</style>
