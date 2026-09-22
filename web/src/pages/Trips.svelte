<script lang="ts">
  import { insights, type SearchResult } from "../lib/api";
  import { app, load } from "../lib/app.svelte";
  import { router } from "../lib/router.svelte";
  import { dateLabel, epochClock } from "../lib/format";
  import ScopeBar from "../lib/ui/ScopeBar.svelte";
  import PageTitle from "../lib/ui/PageTitle.svelte";
  import Panel from "../lib/ui/Panel.svelte";
  import RouteBullet from "../lib/ui/RouteBullet.svelte";
  import NBadge from "../lib/ui/NBadge.svelte";
  import Loading from "../lib/ui/Loading.svelte";

  const res = load(() => { app.tick; return insights.vehicles(router.scopeParams(["to"])); });
  let text = $state("");
  let found = $state<SearchResult | null>(null);
  let timer: ReturnType<typeof setTimeout> | undefined;
  $effect(() => {
    const q = text.trim();
    clearTimeout(timer);
    if (q.length < 2) { found = null; return; }
    timer = setTimeout(() => insights.search(q).then((r) => { if (text.trim() === q) found = r; }).catch(() => {}), 250);
  });
  const date = $derived(router.get("to") ?? app.latest ?? "");
  const rows = $derived.by(() => {
    const q = text.trim().toLowerCase();
    const all = res.data ?? [];
    if (!q) return all;
    return all.filter((v) => v.vehicle_id.toLowerCase().includes(q) || v.routes.some((r) => r.short.toLowerCase() === q));
  });
  const LIMIT = 200;
</script>

<ScopeBar crumbs={[["Trips & vehicles", null]]} show={["dates"]} single />
<PageTitle title="Trips & vehicles" sub={date ? dateLabel(date) : ""} />
<div class="page">
  <div class="search">
    <input type="search" placeholder="Trip ID, vehicle ID or route number" aria-label="Search trips and vehicles" bind:value={text} />
    {#if found && (found.trips.length || found.vehicles.length)}
      <div class="hits">
        {#each found.trips as t}<a class="chip mono" href={router.href(`trip/${t}`)}>trip {t}</a>{/each}
        {#each found.vehicles as v}<a class="chip mono" href={router.href(`vehicle/${v}`, { date: date || undefined })}>vehicle {v}</a>{/each}
      </div>
    {:else if found}
      <span class="muted small">no trip or vehicle IDs match</span>
    {/if}
  </div>
  {#if !res.data}
    <Loading error={res.error} rows={1} />
  {:else}
    <Panel q="Which vehicles ran trips?" info="Vehicles the feed assigned to at least one trip on this service day, busiest first. Click a row for its day." n={rows.length} nLabel="vehicles" warn={false}>
      <table class="t">
        <thead><tr><th>Vehicle</th><th>Routes</th><th class="r">Trips</th><th>First seen</th><th>Last seen</th></tr></thead>
        <tbody>
          {#each rows.slice(0, LIMIT) as v (v.vehicle_id)}
            <tr class="link" onclick={() => router.go(`vehicle/${v.vehicle_id}`, { date: date || undefined })}>
              <td><a class="mono" href={router.href(`vehicle/${v.vehicle_id}`, { date: date || undefined })}>{v.vehicle_id}</a></td>
              <td><span class="rts">{#each v.routes.slice(0, 6) as r}<RouteBullet short={r.short} color={r.color} mode={r.mode} size={20} />{/each}{#if v.routes.length > 6}<span class="muted">+{v.routes.length - 6}</span>{/if}</span></td>
              <td class="r mono">{v.trips}</td>
              <td class="mono">{epochClock(v.t_first, false)}</td>
              <td class="mono">{epochClock(v.t_last, false)}</td>
            </tr>
          {/each}
        </tbody>
      </table>
      {#if rows.length > LIMIT}<div><NBadge n="{rows.length - LIMIT} more · refine the search" /></div>{/if}
    </Panel>
  {/if}
</div>

<style>
  .search { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
  .search input { width: 340px; height: 32px; }
  .hits { display: flex; gap: 6px; flex-wrap: wrap; }
  a.chip { text-decoration: none; }
  .rts { display: inline-flex; gap: 4px; align-items: center; }
</style>
