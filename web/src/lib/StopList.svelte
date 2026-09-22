<script lang="ts">
  import { store, slotColor, type Comparison } from "./store.svelte";
  import { LETTERS } from "./format";

  let { c }: { c: Comparison } = $props();
  let query = $state("");

  const load = $derived(c.routeId ? store.details[c.routeId] : undefined);
  const dir = $derived(store.direction(c));
  const route = $derived(c.routeId ? store.routeById.get(c.routeId) : undefined);
  const fromIdx = $derived(dir?.stations.findIndex((s) => s.station_id === c.from) ?? -1);
  const toIdx = $derived(dir?.stations.findIndex((s) => s.station_id === c.to) ?? -1);
  const rows = $derived.by(() => {
    const q = query.trim().toLowerCase();
    return (dir?.stations ?? []).map((s, i) => ({ s, i })).filter(({ s }) => !q || s.name.toLowerCase().includes(q));
  });

  function role(i: number): "from" | "to" | "between" | null {
    if (i === fromIdx) return "from";
    if (i === toIdx) return "to";
    if (fromIdx >= 0 && toIdx > fromIdx && i > fromIdx && i < toIdx) return "between";
    return null;
  }
</script>

<section class="stops" aria-label="Stops">
  {#if !c.routeId}
    <p class="muted small hint">Choose a route for comparison {LETTERS[c.slot]} to list its stops.</p>
  {:else if load?.status === "loading" || !load}
    <p class="muted small hint">Loading stops…</p>
  {:else if load.status === "error"}
    <p class="small hint">Couldn't load the route: {load.error}</p>
  {:else if dir}
    <div class="head">
      <h2>
        {#if route}<span class="route-badge" style:background="#{route.route_color || '888'}"
          style:color="#{route.route_text_color || 'fff'}">{route.route_short_name}</span>{/if}
        {dir.stations.length} stops → {dir.headsign ?? ""}
      </h2>
      <input type="search" placeholder="Filter stops…" bind:value={query} aria-label="Filter stops" />
    </div>
    <ol style:--c={slotColor(c.slot)}>
      {#each rows as { s, i } (s.station_id)}
        {@const r = role(i)}
        {@const partial = s.n_trips < dir.max_trips * 0.5}
        <li class={r} class:hovered={store.hoverStation === s.station_id}>
          <button onclick={() => store.pickStation(c, s.station_id)}
            onmouseenter={() => (store.hoverStation = s.station_id)}
            onmouseleave={() => (store.hoverStation = null)}
            aria-label="{s.name}{r === 'from' ? ', from' : r === 'to' ? ', to' : ''}">
            <span class="track" class:first={i === 0} class:last={i === dir.stations.length - 1}><span class="node"></span></span>
            <span class="name">
              {s.name}
              {#if i === 0}<span class="note">trip origin: no realtime data</span>
              {:else if partial}<span class="note">{s.n_trips} of {dir.max_trips} trips</span>{/if}
            </span>
            {#if r === "from"}<span class="tag">From</span>{:else if r === "to"}<span class="tag">To</span>{/if}
          </button>
        </li>
      {/each}
    </ol>
  {/if}
</section>

<style>
  .stops { padding: 12px 0 24px; }
  .hint { padding: 0 14px; }
  .head { padding: 0 14px 8px; display: grid; gap: 8px; }
  .head h2 { display: flex; align-items: center; gap: 8px; font-size: 13px; }
  .head input { width: 100%; }
  ol { list-style: none; margin: 0; padding: 0; }
  li button {
    width: 100%; display: flex; align-items: center; gap: 10px; border: 0; background: none;
    text-align: left; padding: 0 14px 0 20px; min-height: 30px;
  }
  li button:hover, li.hovered button { background: var(--surface-2); }
  .track { position: relative; align-self: stretch; width: 12px; flex: none; }
  .track::before { content: ""; position: absolute; left: 5px; top: 0; bottom: 0; width: 2px; background: var(--axis); }
  .track.first::before { top: 50%; }
  .track.last::before { bottom: 50%; }
  .node { position: absolute; left: 1px; top: 50%; width: 10px; height: 10px; margin-top: -5px; border-radius: 50%;
    background: var(--surface); border: 2px solid var(--axis); }
  li.between .track::before, li.from .track::before, li.to .track::before { background: var(--c); width: 4px; left: 4px; }
  li.from .track::before { top: 50%; }
  li.to .track::before { bottom: 50%; }
  li.from .node, li.to .node { background: var(--c); border-color: var(--surface); width: 14px; height: 14px;
    left: -1px; margin-top: -7px; box-shadow: 0 0 0 1px var(--c); }
  li.between .node { border-color: var(--c); }
  .name { flex: 1; min-width: 0; padding: 5px 0; font-size: 13px; }
  li.from .name, li.to .name { font-weight: 600; }
  .note { display: block; font-size: 11px; color: var(--muted); }
  .tag { font-size: 11px; font-weight: 600; color: var(--ink-2); border: 1px solid var(--border); border-radius: 999px;
    padding: 0 7px; }
</style>
