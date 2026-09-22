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
    <span class="bullet lg">{LETTERS[c.slot]}</span>
    <select aria-label="Route for comparison {LETTERS[c.slot]}" value={c.routeId ?? ""}
      onchange={(e) => store.setRoute(c, (e.currentTarget as HTMLSelectElement).value || null)}>
      <option value="">Choose a route…</option>
      {#each groups as [type, routes]}
        <optgroup label={MODE_NAMES[type] ?? `Mode ${type}`}>
          {#each routes as r}<option value={r.route_id}>{routeLabel(r)}</option>{/each}
        </optgroup>
      {/each}
    </select>
    <div class="tools">
      <button class="icon-btn" title="Show on map" aria-label="Zoom map to comparison {LETTERS[c.slot]}"
        onclick={(e) => { e.stopPropagation(); store.focus(c.id); }} disabled={!c.routeId}>
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" aria-hidden="true">
          <circle cx="8" cy="8" r="4.5" /><circle cx="8" cy="8" r="1.2" fill="currentColor" /><path d="M8 1v2M8 13v2M1 8h2M13 8h2" />
        </svg>
      </button>
      <button class="icon-btn" title="Duplicate (then change the route to compare the same stops)"
        aria-label="Duplicate comparison {LETTERS[c.slot]}" onclick={(e) => { e.stopPropagation(); store.duplicate(c.id); }}
        disabled={!c.routeId}>
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" aria-hidden="true">
          <rect x="5.5" y="5.5" width="8.5" height="8.5" rx="2" /><path d="M10.5 3.5V3a1.5 1.5 0 0 0-1.5-1.5H3.5A1.5 1.5 0 0 0 2 3v5.5A1.5 1.5 0 0 0 3.5 10H4" />
        </svg>
      </button>
      <button class="icon-btn" title="Remove" aria-label="Remove comparison {LETTERS[c.slot]}"
        onclick={(e) => { e.stopPropagation(); store.remove(c.id); }}>
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" aria-hidden="true">
          <path d="M4 4l8 8M12 4l-8 8" />
        </svg>
      </button>
    </div>
  </div>

  {#if detail && detail.directions.length > 1}
    <div class="seg dirs" role="group" aria-label="Direction">
      {#each detail.directions as d}
        <button aria-pressed={c.directionId === d.direction_id}
          onclick={(e) => { e.stopPropagation(); store.setDirection(c, d.direction_id); }}>
          {d.headsign ?? `Direction ${d.direction_id}`}
        </button>
      {/each}
    </div>
  {/if}

  {#if c.routeId}
    {#if c.from}
      <ol class="trip" aria-label="Segment">
        <li><span class="stop"></span><span class="st">{stationName(c.from) ?? c.from}</span></li>
        <li class:pending={!c.to}><span class="stop"></span>
          <span class="st">{c.to ? (stationName(c.to) ?? c.to) : "Now pick where you get off"}</span></li>
      </ol>
    {:else}
      <p class="hint">{active ? "Pick where you get on, from the list below or the map" : "Tap to pick stops"}</p>
    {/if}
    {#if seg?.status === "error"}<p class="small err">{seg.error}</p>{/if}
  {:else}
    <p class="hint">Start by choosing a bus or train line</p>
  {/if}
</div>

<style>
  .card { padding: 12px; display: grid; grid-template-columns: minmax(0, 1fr); gap: 10px; cursor: pointer;
    box-shadow: none; border-width: 1.5px; transition: border-color .15s, box-shadow .15s; }
  .card:hover { border-color: var(--border-strong); }
  .card.active { border-color: var(--c); box-shadow: 0 0 0 3px color-mix(in srgb, var(--c) 16%, transparent); }
  .row { display: flex; align-items: center; gap: 10px; }
  select { flex: 1; min-width: 0; font-weight: 600; }
  .tools { display: flex; margin-right: -4px; }
  .dirs { display: flex; min-width: 0; }
  .dirs button { flex: 1; overflow: hidden; text-overflow: ellipsis; min-width: 0; }
  .trip { list-style: none; margin: 0; padding: 0 0 0 9px; display: grid; gap: 4px; }
  .trip li { display: flex; align-items: center; gap: 12px; position: relative; font-size: 13.5px; }
  .trip li:first-child::after { content: ""; position: absolute; left: 4px; top: 13px; height: calc(100% + 1px);
    width: 4px; background: var(--c); }
  .stop { width: 12px; height: 12px; border-radius: 50%; background: var(--surface); border: 3px solid var(--c);
    flex: none; position: relative; z-index: 1; }
  .st { font-weight: 600; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .pending .st { font-weight: 500; color: var(--muted); font-style: italic; }
  .pending .stop { border-style: dashed; border-color: var(--axis); }
  .hint { font-size: 13px; color: var(--muted); padding-left: 2px; }
  .err { color: var(--critical); }
</style>
