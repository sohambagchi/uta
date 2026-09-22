<script lang="ts">
  import { store, slotColor, type Comparison } from "./store.svelte";
  import { LETTERS, MODE_NAMES, routeLabel } from "./format";

  let { c }: { c: Comparison } = $props();

  const active = $derived(store.activeId === c.id);
  const detail = $derived(store.detail(c));
  const dir = $derived(store.direction(c));
  const stationName = (id: string | null) => dir?.stations.find((s) => s.station_id === id)?.name ?? null;
  const groups = $derived.by(() => {
    const m = new Map<number, typeof store.routes>();
    for (const r of store.routes) {
      if (!r.directions.length) continue;
      if (!m.has(r.route_type)) m.set(r.route_type, []);
      m.get(r.route_type)!.push(r);
    }
    return [...m.entries()].sort((a, b) => a[0] - b[0]);
  });
  const seg = $derived(store.segment(c));
</script>

<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
<div class="card" class:active onclick={() => (store.activeId = c.id)} style:--c={slotColor(c.slot)}>
  <div class="row">
    <span class="key" style:background={slotColor(c.slot)}></span>
    <strong class="letter">{LETTERS[c.slot]}</strong>
    <select aria-label="Route for comparison {LETTERS[c.slot]}" value={c.routeId ?? ""}
      onchange={(e) => store.setRoute(c, (e.currentTarget as HTMLSelectElement).value || null)}>
      <option value="">Choose a route…</option>
      {#each groups as [type, routes]}
        <optgroup label={MODE_NAMES[type] ?? `Mode ${type}`}>
          {#each routes as r}<option value={r.route_id}>{routeLabel(r)}</option>{/each}
        </optgroup>
      {/each}
    </select>
    <button class="icon-btn" title="Zoom map to this segment" aria-label="Zoom map to comparison {LETTERS[c.slot]}"
      onclick={(e) => { e.stopPropagation(); store.focus(c.id); }} disabled={!c.routeId}>⌖</button>
    <button class="icon-btn" title="Duplicate (then change the route to compare the same stops)"
      aria-label="Duplicate comparison {LETTERS[c.slot]}" onclick={(e) => { e.stopPropagation(); store.duplicate(c.id); }}
      disabled={!c.routeId}>⧉</button>
    <button class="icon-btn" title="Remove" aria-label="Remove comparison {LETTERS[c.slot]}"
      onclick={(e) => { e.stopPropagation(); store.remove(c.id); }}>×</button>
  </div>

  {#if detail && detail.directions.length > 1}
    <div class="seg dirs" role="group" aria-label="Direction">
      {#each detail.directions as d}
        <button aria-pressed={c.directionId === d.direction_id}
          onclick={(e) => { e.stopPropagation(); store.setDirection(c, d.direction_id); }}>
          → {d.headsign ?? `Direction ${d.direction_id}`}
        </button>
      {/each}
    </div>
  {/if}

  {#if c.routeId}
    <div class="pair small">
      {#if c.from}
        <span class="st">{stationName(c.from) ?? c.from}</span>
        <span class="muted">→</span>
        <span class="st">{c.to ? (stationName(c.to) ?? c.to) : "pick a downstream stop"}</span>
      {:else}
        <span class="muted">{active ? "Pick two stops in the list below or on the map" : "Select to pick stops"}</span>
      {/if}
    </div>
    {#if seg?.status === "error"}<p class="small err">{seg.error}</p>{/if}
  {/if}
</div>

<style>
  .card { min-width: 0; border: 1px solid var(--border); border-radius: var(--radius); padding: 8px 8px 8px 10px;
    background: var(--surface); display: grid; grid-template-columns: minmax(0, 1fr); gap: 6px; cursor: pointer; position: relative; }
  .card.active { border-color: var(--c); box-shadow: inset 3px 0 0 var(--c); }
  .row { display: flex; align-items: center; gap: 6px; }
  .letter { font-size: 12px; width: 12px; }
  select { flex: 1; min-width: 0; padding: 3px 6px; }
  .dirs { display: flex; min-width: 0; }
  .dirs button { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; }
  .pair { display: flex; gap: 6px; flex-wrap: wrap; color: var(--ink-2); }
  .st { font-weight: 500; color: var(--ink); }
  .err { color: var(--critical); }
  .icon-btn:disabled { opacity: .35; cursor: default; }
</style>
