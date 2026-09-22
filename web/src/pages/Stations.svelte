<script lang="ts">
  import { insights, type SearchResult } from "../lib/api";
  import { load } from "../lib/app.svelte";
  import { router } from "../lib/router.svelte";
  import { title } from "../lib/format";
  import ScopeBar from "../lib/ui/ScopeBar.svelte";
  import PageTitle from "../lib/ui/PageTitle.svelte";
  import Panel from "../lib/ui/Panel.svelte";
  import RouteBullet from "../lib/ui/RouteBullet.svelte";
  import Tag from "../lib/ui/Tag.svelte";
  import Loading from "../lib/ui/Loading.svelte";

  const hubs = load(() => insights.hubs());
  let q = $state("");
  let found = $state<SearchResult | null>(null);
  let timer: ReturnType<typeof setTimeout>;
  $effect(() => {
    const text = q.trim();
    clearTimeout(timer);
    if (!text) { found = null; return; }
    timer = setTimeout(() => insights.search(text).then((r) => { if (q.trim() === text) found = r; }), 200);
  });
  const short = (n: string) => n.replace(/ Station$/, "");
</script>

<ScopeBar crumbs={[["Stations", null]]} show={["dates"]} />
<PageTitle title="Stations" />
<div class="page">
  <div class="row wrap-md">
    <div class="side"><Panel q="Find a station">
      <input type="search" placeholder="Station or route" bind:value={q} aria-label="Search stations and routes" />
      {#if found}
        {#if found.stations.length}
          <ul class="list">
            {#each found.stations as s}
              <li><a href={router.href(`stations/${s.station_id}`)}>{short(s.name)}</a><span class="muted">{s.n_stops} stops</span></li>
            {/each}
          </ul>
        {/if}
        {#if found.routes.length}
          <ul class="list">
            {#each found.routes as r}
              <li><a class="rn" href={router.href(`routes/${r.route_id}/0`)}><RouteBullet short={r.short} color={r.color} mode={r.mode} size={20} /><span>{title(r.long)}</span></a></li>
            {/each}
          </ul>
        {/if}
        {#if !found.stations.length && !found.routes.length}<Tag>no match</Tag>{/if}
      {/if}
    </Panel></div>

    <Panel q="Which stations are the biggest hubs?" info="Stations served by the most routes." grow>
      {#if hubs.data}
        <table class="t">
          <thead><tr><th>Station</th><th class="r">Routes</th><th class="r">Stops</th></tr></thead>
          <tbody>
            {#each hubs.data as h (h.station_id)}
              <tr class="link" onclick={() => router.go(`stations/${h.station_id}`)}>
                <td><a href={router.href(`stations/${h.station_id}`)}>{short(h.name)}</a></td>
                <td class="r">{h.n_routes}</td>
                <td class="r">{h.n_stops}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      {:else}
        <Loading error={hubs.error} rows={1} />
      {/if}
    </Panel>
  </div>
</div>

<style>
  .side { width: 460px; flex-shrink: 0; align-self: flex-start; }
  @media (max-width: 1100px) { .side { width: auto; align-self: stretch; } }
  input[type="search"] { width: 100%; height: 32px; }
  .list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; }
  .list li { display: flex; justify-content: space-between; gap: 8px; padding: 6px 2px; border-bottom: 1px solid var(--grid); }
  .rn { display: inline-flex; align-items: center; gap: 8px; color: var(--ink); }
  table a { color: var(--ink); }
</style>
