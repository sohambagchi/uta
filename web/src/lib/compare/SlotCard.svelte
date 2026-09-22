<script lang="ts">
  // One comparison: slot bullet, route picker, direction, the chosen stretch on a mini strip, and its headline.
  import { store, type Comparison } from "../store.svelte";
  import { LETTERS, MODE_NAMES, routeLabel, dur } from "../format";
  import type { Series } from "../series";
  import Slot from "../ui/Slot.svelte";
  import RouteBullet from "../ui/RouteBullet.svelte";
  import NBadge from "../ui/NBadge.svelte";
  import Tag from "../ui/Tag.svelte";

  let { c, s }: { c: Comparison; s: Series | undefined } = $props();

  const active = $derived(store.activeId === c.id);
  const route = $derived(c.routeId ? store.routeById.get(c.routeId) : undefined);
  const detail = $derived(store.detail(c));
  const dir = $derived(store.direction(c));
  const name = (id: string | null) => dir?.stations.find((x) => x.station_id === id)?.name?.replace(/ Station$/, "") ?? null;
  const between = $derived(store.between(c).size);
  const seg = $derived(store.segment(c));
  const groups = $derived.by(() => {
    const m = new Map<number, typeof store.routes>();
    for (const r of store.routes) {
      if (!r.directions.length) continue;
      if (!m.has(r.route_type)) m.set(r.route_type, []);
      m.get(r.route_type)!.push(r);
    }
    return [...m.entries()].sort((a, b) => a[0] - b[0]);
  });
  const mode = (t: number | undefined) => (t === 3 ? "bus" : t === 2 ? "rail" : "lrt");
  const W = 290;
  // stretch drawn with at most 8 intermediate nodes
  const nodes = $derived(Math.min(between, 8) + 2);
  const sx = (i: number) => 10 + (i * (W - 20)) / Math.max(1, nodes - 1);
</script>

<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
<div class="card" class:active style:--c="var(--slot-{c.slot + 1})" onclick={() => (store.activeId = c.id)}>
  <div class="top">
    <Slot i={c.slot} size={24} />
    {#if route}<RouteBullet short={route.route_short_name} color={route.route_color} mode={mode(route.route_type)} size={22} />{/if}
    <select aria-label="Route for comparison {LETTERS[c.slot]}" value={c.routeId ?? ""}
      onclick={(e) => e.stopPropagation()}
      onchange={(e) => store.setRoute(c, (e.currentTarget as HTMLSelectElement).value || null)}>
      <option value="">Choose a route…</option>
      {#each groups as [type, routes]}
        <optgroup label={MODE_NAMES[type] ?? `Mode ${type}`}>
          {#each routes as r}<option value={r.route_id}>{routeLabel(r)}</option>{/each}
        </optgroup>
      {/each}
    </select>
    <div class="tools">
      <button class="icon-btn" title="Show on map" aria-label="Zoom map to comparison {LETTERS[c.slot]}" disabled={!c.routeId}
        onclick={(e) => { e.stopPropagation(); store.focus(c.id); }}>
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" aria-hidden="true">
          <circle cx="8" cy="8" r="4.5" /><circle cx="8" cy="8" r="1.2" fill="currentColor" /><path d="M8 1v2M8 13v2M1 8h2M13 8h2" /></svg>
      </button>
      <button class="icon-btn" title="Duplicate" aria-label="Duplicate comparison {LETTERS[c.slot]}" disabled={!c.routeId || store.comparisons.length >= 4}
        onclick={(e) => { e.stopPropagation(); store.duplicate(c.id); }}>
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" aria-hidden="true">
          <rect x="5.5" y="5.5" width="8.5" height="8.5" rx="1.5" /><path d="M10.5 3.5V2.5a1 1 0 0 0-1-1h-7a1 1 0 0 0-1 1v7a1 1 0 0 0 1 1h1.5" /></svg>
      </button>
      <button class="icon-btn" title="Remove" aria-label="Remove comparison {LETTERS[c.slot]}"
        onclick={(e) => { e.stopPropagation(); store.remove(c.id); }}>
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" aria-hidden="true"><path d="M4 4l8 8M12 4l-8 8" /></svg>
      </button>
    </div>
  </div>

  {#if detail && detail.directions.length > 1}
    <div class="seg dirs" role="group" aria-label="Direction">
      {#each detail.directions as d}
        <button aria-pressed={c.directionId === d.direction_id} title={d.headsign ?? ""}
          onclick={(e) => { e.stopPropagation(); store.setDirection(c, d.direction_id); }}>{(d.headsign ?? `Direction ${d.direction_id}`).replace(/^To /, "")}</button>
      {/each}
    </div>
  {/if}

  {#if c.routeId && c.from && c.to}
    <svg class="chart strip" width={W} height="42" viewBox="0 0 {W} 42" role="img" aria-label="{name(c.from)} to {name(c.to)}">
      <line x1={sx(0)} x2={sx(nodes - 1)} y1="12" y2="12" stroke="var(--c)" stroke-width="5" />
      {#each Array(nodes) as _, i}
        {@const end = i === 0 || i === nodes - 1}
        <circle cx={sx(i)} cy="12" r={end ? 5.5 : 3.2} fill={end ? "var(--c)" : "var(--panel)"} stroke={end ? "var(--panel)" : "var(--c)"} stroke-width="2" />
      {/each}
      <text x={sx(0)} y="35" style="fill: var(--ink); font-size: 11px; font-weight: 600">{name(c.from)}</text>
      <text x={sx(nodes - 1)} y="35" text-anchor="end" style="fill: var(--ink); font-size: 11px; font-weight: 600">{name(c.to)}</text>
    </svg>
    <div class="foot">
      {#if s?.obs}<span>median <b>{dur(s.obs.median)}</b></span>{:else if seg?.status === "loading"}<span class="muted">loading…</span>{:else}<Tag kind="hatch">no observed trips</Tag>{/if}
      {#if s?.schedMedian != null}<span class="muted">timetable {dur(s.schedMedian)}</span>{/if}
      <span class="sp"></span>
      {#if s}<NBadge n={s.trips.length} warn={s.trips.length < 20} />{/if}
    </div>
  {:else if c.routeId}
    <div class="foot"><Tag>{c.from ? `from ${name(c.from)} · pick To` : "pick From on the strip"}</Tag></div>
  {/if}
  {#if seg?.status === "error"}<Tag kind="bad">{seg.error}</Tag>{/if}
</div>

<style>
  .card { background: var(--panel); border: 1px solid var(--border); border-radius: 6px; padding: 11px 12px; display: flex;
    flex-direction: column; gap: 9px; cursor: pointer; min-width: 0; }
  .card:hover { border-color: var(--axis); }
  .card.active { border-color: var(--c); box-shadow: inset 3px 0 0 var(--c); }
  .top { display: flex; align-items: center; gap: 7px; min-width: 0; }
  select { flex: 1; min-width: 0; font-weight: 600; font-size: 12.5px; }
  .tools { display: flex; gap: 3px; }
  .dirs { display: flex; min-width: 0; }
  .dirs button { flex: 1 1 0; min-width: 0; overflow: hidden; text-overflow: ellipsis; height: 28px; }
  .strip { max-width: 100%; height: auto; }
  .foot { display: flex; align-items: center; gap: 10px; font-size: 12px; color: var(--ink-2); flex-wrap: wrap; }
  .foot b { color: var(--ink); font-weight: 650; }
  .sp { flex: 1; }
</style>
