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
  // while choosing a To stop, grey out stops no trip reaches from From
  const reach = $derived(c.from && !c.to ? store.reachable(c) : null);
  const onPath = $derived(store.between(c));
  const rows = $derived.by(() => {
    const q = query.trim().toLowerCase();
    return (dir?.stations ?? []).map((s, i) => ({ s, i })).filter(({ s }) => !q || s.name.toLowerCase().includes(q));
  });

  const prompt = $derived(!c.from ? "Tap the stop where you get on" : !c.to ? "Now tap where you get off"
    : "Tap any stop to start over");

  function role(i: number): "from" | "to" | "between" | null {
    if (i === fromIdx) return "from";
    if (i === toIdx) return "to";
    if (onPath.has(i)) return "between";
    return null;
  }
</script>

<section class="stops" aria-label="Stops">
  {#if !c.routeId}
    <p class="muted small hint">Once you pick a line, its stops show up here.</p>
  {:else if load?.status === "loading" || !load}
    <p class="muted small hint">Loading stops…</p>
  {:else if load.status === "error"}
    <p class="small hint">Couldn't load the route: {load.error}</p>
  {:else if dir}
    <div class="head">
      <h2>
        {#if route}<span class="route-badge" style:background="#{route.route_color || '888'}"
          style:color="#{route.route_text_color || 'fff'}">{route.route_short_name}</span>{/if}
        <span class="toward"><span class="muted">toward</span> {dir.headsign ?? "—"}</span>
        <span class="count muted">{dir.stations.length} stops</span>
      </h2>
      <p class="prompt" style:--c={slotColor(c.slot)}><span class="bullet sm">{LETTERS[c.slot]}</span>{prompt}</p>
      <input type="search" placeholder="Find a stop…" bind:value={query} aria-label="Filter stops" />
      {#if reach && reach.size < dir.stations.length - 1}
        <p class="small muted">Faded stops aren't served by any trip from {dir.stations[fromIdx]?.name}. Tapping one starts over from it.</p>
      {/if}
    </div>
    <ol style:--c={slotColor(c.slot)}>
      {#each rows as { s, i } (s.station_id)}
        {@const r = role(i)}
        {@const partial = s.n_trips < dir.max_trips * 0.5}
        {@const unreachable = reach != null && i !== fromIdx && !reach.has(i)}
        <li class={r} class:hovered={store.hoverStation === s.station_id} class:unreachable>
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
            {#if r === "from"}<span class="tag">Get on</span>{:else if r === "to"}<span class="tag">Get off</span>{/if}
          </button>
        </li>
      {/each}
    </ol>
  {/if}
</section>

<style>
  .stops { padding: 16px 0 28px; }
  .hint { padding: 0 18px; }
  .head { padding: 0 16px 10px; display: grid; gap: 10px; }
  .head h2 { display: flex; align-items: center; gap: 8px; font-size: 15px; min-width: 0; }
  .toward { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .toward .muted { font-weight: 500; }
  .count { margin-left: auto; font-size: 12.5px; font-weight: 500; white-space: nowrap; }
  .prompt { display: flex; align-items: center; gap: 8px; font-size: 13.5px; font-weight: 600; padding: 8px 10px;
    border-radius: var(--radius-sm); background: color-mix(in srgb, var(--c) 9%, var(--surface)); }
  .head input { width: 100%; padding-left: 34px;
    background: var(--surface) url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 16 16' fill='none' stroke='%23888' stroke-width='1.7' stroke-linecap='round'%3E%3Ccircle cx='7' cy='7' r='4.5'/%3E%3Cpath d='m10.5 10.5 3 3'/%3E%3C/svg%3E") no-repeat 11px center; }
  ol { list-style: none; margin: 0; padding: 0; }
  li button {
    width: 100%; display: flex; align-items: center; gap: 12px; border: 0; background: none;
    text-align: left; padding: 0 16px 0 22px; min-height: 34px; transition: background .1s;
  }
  li button:hover, li.hovered button { background: var(--surface-2); }
  /* strip map: a thick line with station dots, colored along the chosen stretch */
  .track { position: relative; align-self: stretch; width: 18px; flex: none; }
  .track::before { content: ""; position: absolute; left: 6px; top: 0; bottom: 0; width: 6px; background: var(--surface-3); }
  .track.first::before { top: 50%; }
  .track.last::before { bottom: 50%; }
  .node { position: absolute; left: 3px; top: 50%; width: 12px; height: 12px; margin-top: -6px; border-radius: 50%;
    background: var(--surface); border: 2.5px solid var(--axis); transition: transform .12s; }
  li button:hover .node { transform: scale(1.2); }
  li.between .track::before, li.from .track::before, li.to .track::before { background: var(--c); }
  li.from .track::before { top: 50%; }
  li.to .track::before { bottom: 50%; }
  li.from .node, li.to .node { width: 20px; height: 20px; left: -1px; margin-top: -10px; background: var(--surface);
    border: 4.5px solid var(--ink); }
  li.between .node { border-color: var(--c); }
  li.unreachable .name { color: var(--muted); opacity: .7; }
  li.unreachable .node { border-color: var(--grid); }
  .name { flex: 1; min-width: 0; padding: 6px 0; font-size: 14px; }
  li.from .name, li.to .name { font-weight: 700; }
  .note { display: block; font-size: 11.5px; color: var(--muted); }
  .tag { font-size: 11.5px; font-weight: 700; color: #fff; background: var(--c); border-radius: 999px;
    padding: 2px 9px; white-space: nowrap; }
</style>
