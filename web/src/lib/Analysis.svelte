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
    <div class="empty">
      {#if loading}
        <p class="muted">Loading trips…</p>
      {:else}
        <p><strong>Pick a route and two stops</strong> in the left column (or click stops on the map). You'll get
          observed and scheduled travel times between them, how they vary by time of day and day of week, and
          how spread out they are.</p>
        <p class="muted">Add up to four comparisons: different routes over the same stops, or different stretches of one
          route. Observed times come from the realtime feed and cover the period the collector has been running.</p>
      {/if}
    </div>
  {:else}
    <div class="legend" class:loading aria-label="Comparisons">
      {#each series as s (s.c.id)}
        <button class="item" class:active={s.c.id === store.activeId} onclick={() => (store.activeId = s.c.id)}>
          <span class="key" style:background={s.color}></span>
          <strong>{s.letter}</strong> {s.label}
        </button>
      {/each}
      {#if pending}<span class="muted small">{pending} comparison{pending > 1 ? "s" : ""} still need stops</span>{/if}
    </div>

    <div class:loading>
      <SummaryTable {series} />
      <Charts {series} active={activeSeries} bin={store.filters.bin} />
      {#if activeSeries}<TripsTable s={activeSeries} />{/if}
    </div>
  {/if}
</div>

<style>
  .analysis { padding: 16px 20px 48px; display: grid; grid-template-columns: minmax(0, 1fr); gap: 16px; max-width: 1600px; }
  .empty { background: var(--surface); border: 1px dashed var(--axis); border-radius: var(--radius); padding: 24px;
    max-width: 720px; display: grid; gap: 10px; }
  .legend { display: flex; flex-wrap: wrap; gap: 6px 10px; align-items: center; }
  .item { display: inline-flex; align-items: center; gap: 6px; border: 1px solid transparent; background: none;
    border-radius: 8px; padding: 3px 8px; font-size: 13px; color: var(--ink-2); }
  .item strong { color: var(--ink); }
  .item.active { border-color: var(--border); background: var(--surface); color: var(--ink); }
  .loading { opacity: .5; transition: opacity .15s; }
</style>
