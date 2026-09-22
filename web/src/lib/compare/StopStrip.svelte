<script lang="ts">
  // The active comparison's stations as a vertical strip map: first tap is From, second is To.
  import { store, type Comparison } from "../store.svelte";
  import Slot from "../ui/Slot.svelte";
  import RouteBullet from "../ui/RouteBullet.svelte";
  import Tag from "../ui/Tag.svelte";

  let { c }: { c: Comparison } = $props();
  let query = $state("");

  const load = $derived(c.routeId ? store.details[c.routeId] : undefined);
  const dir = $derived(store.direction(c));
  const route = $derived(c.routeId ? store.routeById.get(c.routeId) : undefined);
  const fromIdx = $derived(dir?.stations.findIndex((s) => s.station_id === c.from) ?? -1);
  const toIdx = $derived(dir?.stations.findIndex((s) => s.station_id === c.to) ?? -1);
  // while choosing To, stops no trip reaches from From are faded
  const reach = $derived(c.from && !c.to ? store.reachable(c) : null);
  const onPath = $derived(store.between(c));
  const rows = $derived.by(() => {
    const q = query.trim().toLowerCase();
    return (dir?.stations ?? []).map((s, i) => ({ s, i })).filter(({ s }) => !q || s.name.toLowerCase().includes(q));
  });
  const step = $derived(!c.from ? "pick From" : !c.to ? "pick To" : "tap to restart");
  const mode = (t: number | undefined) => (t === 3 ? "bus" : t === 2 ? "rail" : "lrt");

  function role(i: number): "from" | "to" | "between" | null {
    if (i === fromIdx) return "from";
    if (i === toIdx) return "to";
    if (onPath.has(i)) return "between";
    return null;
  }
</script>

<section class="stops" aria-label="Stops" style:--c="var(--slot-{c.slot + 1})">
  {#if !c.routeId}
    <div class="head"><Tag>pick a route above</Tag></div>
  {:else if !load || load.status === "loading"}
    <div class="head"><Tag>loading stops…</Tag></div>
  {:else if load.status === "error"}
    <div class="head"><Tag kind="bad">{load.error}</Tag></div>
  {:else if dir}
    <div class="head">
      <div class="title">
        {#if route}<RouteBullet short={route.route_short_name} color={route.route_color} mode={mode(route.route_type)} size={22} />{/if}
        <span class="toward"><span class="muted">toward</span> {(dir.headsign ?? "—").replace(/^To /, "")}</span>
        <span class="count">{dir.stations.length} stops</span>
      </div>
      <div class="step"><Slot i={c.slot} size={18} /><b>{step}</b>
        {#if reach && reach.size < dir.stations.length - 1}<span class="muted small">faded: not reached from From</span>{/if}</div>
      <input type="search" placeholder="Find a stop" bind:value={query} aria-label="Filter stops" />
    </div>
    <ol>
      {#each rows as { s, i } (s.station_id)}
        {@const r = role(i)}
        {@const partial = s.n_trips < dir.max_trips * 0.5}
        {@const unreachable = reach != null && i !== fromIdx && !reach.has(i)}
        <li class={r} class:hovered={store.hoverStation === s.station_id} class:unreachable>
          <button onclick={() => store.pickStation(c, s.station_id)} onmouseenter={() => (store.hoverStation = s.station_id)}
            onmouseleave={() => (store.hoverStation = null)} aria-label="{s.name}{r === 'from' ? ', from' : r === 'to' ? ', to' : ''}">
            <span class="track" class:first={i === 0} class:last={i === dir.stations.length - 1}><span class="node"></span></span>
            <span class="name">{s.name.replace(/ Station$/, "")}</span>
            {#if i === 0}<span class="note">no realtime</span>{:else if partial}<span class="note">{s.n_trips}/{dir.max_trips} trips</span>{/if}
            {#if r === "from"}<span class="role">From</span>{:else if r === "to"}<span class="role">To</span>{/if}
          </button>
        </li>
      {/each}
    </ol>
  {/if}
</section>

<style>
  .stops { padding: 14px 0 24px; }
  .head { padding: 0 16px 8px; display: flex; flex-direction: column; gap: 9px; }
  .title { display: flex; align-items: center; gap: 8px; font-size: 13.5px; font-weight: 650; min-width: 0; }
  .toward { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .toward .muted { font-weight: 450; }
  .count { margin-left: auto; font-size: 12px; color: var(--muted); font-weight: 450; white-space: nowrap; }
  .step { display: flex; align-items: center; gap: 8px; font-size: 12.5px; padding: 6px 8px; border-radius: 4px;
    background: color-mix(in srgb, var(--c) 10%, var(--panel)); flex-wrap: wrap; }
  .step b { font-weight: 650; }
  input { width: 100%; }
  ol { list-style: none; margin: 0; padding: 0; }
  li button { width: 100%; display: flex; align-items: center; gap: 10px; border: 0; background: none; text-align: left;
    padding: 0 14px 0 18px; min-height: 30px; font-size: 13px; }
  li button:hover, li.hovered button { background: var(--panel-2); }
  .track { position: relative; align-self: stretch; width: 18px; flex: none; }
  .track::before { content: ""; position: absolute; left: 6px; top: 0; bottom: 0; width: 5px; background: var(--sunk); }
  .track.first::before { top: 50%; }
  .track.last::before { bottom: 50%; }
  .node { position: absolute; left: 3px; top: 50%; width: 11px; height: 11px; margin-top: -5.5px; border-radius: 50%;
    background: var(--panel); border: 2px solid var(--axis); }
  li.between .track::before, li.from .track::before, li.to .track::before { background: var(--c); }
  li.from .track::before { top: 50%; }
  li.to .track::before { bottom: 50%; }
  li.from .node, li.to .node { width: 17px; height: 17px; left: 0; margin-top: -8.5px; background: var(--c); border: 3px solid var(--panel);
    box-shadow: 0 0 0 1.5px var(--c); }
  li.between .node { border-color: var(--c); }
  li.unreachable .name { color: var(--faint); }
  li.unreachable .node { border-color: var(--grid); }
  .name { flex: 1; min-width: 0; padding: 5px 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  li.from .name, li.to .name { font-weight: 650; }
  .note { font-size: 11px; color: var(--muted); white-space: nowrap; }
  .role { font-size: 11px; font-weight: 650; color: #fff; background: var(--c); border-radius: 3px; height: 20px; padding: 0 7px;
    display: inline-flex; align-items: center; }
</style>
