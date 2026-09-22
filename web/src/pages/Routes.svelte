<script lang="ts">
  import { insights } from "../lib/api";
  import { app, load } from "../lib/app.svelte";
  import { router } from "../lib/router.svelte";
  import { delay, pct, MODE_LABEL, title } from "../lib/format";
  import ScopeBar from "../lib/ui/ScopeBar.svelte";
  import PageTitle from "../lib/ui/PageTitle.svelte";
  import Panel from "../lib/ui/Panel.svelte";
  import RouteBullet from "../lib/ui/RouteBullet.svelte";
  import DelayCell from "../lib/ui/DelayCell.svelte";
  import Sparkline from "../lib/ui/Sparkline.svelte";
  import NBadge from "../lib/ui/NBadge.svelte";
  import Loading from "../lib/ui/Loading.svelte";

  // same rule as the backend (insights.mode_of): route_type 0 is TRAX, except the S-Line streetcar
  const mode_of = (t: number, short: string) => (t === 2 ? "rail" : t === 0 ? (short === "720" ? "streetcar" : "lrt") : "bus");
  $effect(() => { app.loadNetwork(); });
  const res = load(() => { app.tick; return insights.network(router.scopeParams()); });
  let filter = $state(router.get("q") ?? "");
  const stats = $derived(new Map((res.data?.routes ?? []).map((r) => [r.route_id, r])));
  const ORDER = ["rail", "lrt", "streetcar", "bus"];
  const groups = $derived.by(() => {
    const f = filter.trim().toLowerCase();
    const rows = app.routes
      .map((r) => ({ r, mode: mode_of(r.route_type, r.route_short_name), s: stats.get(r.route_id) }))
      .filter(({ r }) => !f || r.route_short_name.toLowerCase().includes(f) || (r.route_long_name ?? "").toLowerCase().includes(f));
    return ORDER.map((m) => ({ m, rows: rows.filter((x) => x.mode === m) })).filter((g) => g.rows.length);
  });
</script>

<ScopeBar crumbs={[["Network", router.href("network")], ["Routes", null]]} show={["dates", "days", "hours", "otp"]} />
<PageTitle title="Routes" sub="{app.routes.length} routes">
  {#snippet right()}
    <input type="search" placeholder="Filter" aria-label="Filter routes" bind:value={filter} oninput={() => router.set({ q: filter || null })} />
  {/snippet}
</PageTitle>
{#if !app.routes.length}
  <Loading error={res.error} rows={2} />
{:else}
  <div class="page" class:dim={res.loading}>
    {#each groups as g (g.m)}
      <Panel q={MODE_LABEL[g.m]} n={g.rows.length} nLabel="routes" warn={false}>
        <table class="t fixed">
          <colgroup><col style="width: 28%" /><col /><col style="width: 120px" /><col style="width: 90px" /><col style="width: 70px" /><col style="width: 56px" /><col style="width: 88px" /></colgroup>
          <thead><tr><th>Route</th><th>Directions</th><th>On time</th><th class="r">Median</th><th>By hour</th><th class="r">Trips</th><th class="r">Visits</th></tr></thead>
          <tbody>
            {#each g.rows as { r, s } (r.route_id)}
              <tr class="link" onclick={() => router.go(`routes/${r.route_id}/${r.directions[0]?.direction_id ?? 0}`)}>
                <td><a class="rn" href={router.href(`routes/${r.route_id}/${r.directions[0]?.direction_id ?? 0}`)}>
                  <RouteBullet short={r.route_short_name} color={r.route_color} mode={g.m} size={20} /><span>{title(r.route_long_name)}</span></a></td>
                <td class="dirs">
                  {#each r.directions as d}
                    <a href={router.href(`routes/${r.route_id}/${d.direction_id}`)} onclick={(e) => e.stopPropagation()}>{d.headsign ?? d.direction_id}</a>
                  {/each}
                </td>
                {#if s && s.n}
                  <td><span class="ot"><span class="bar"><span style:width="{(s.otp ?? 0) * 100}%"></span></span><b>{pct(s.otp, 0)}</b></span></td>
                  <td class="r"><DelayCell s={s.median} /></td>
                  <td><Sparkline vals={s.spark} w={50} h={18} lo={0.3} hi={1} /></td>
                  <td class="r mono">{s.trips}</td>
                  <td class="r"><NBadge n={s.n} /></td>
                {:else if res.loading && !res.data}
                  <td colspan="5"><span class="sk"></span></td>
                {:else}
                  <td colspan="5" class="none">no observed visits</td>
                {/if}
              </tr>
            {/each}
          </tbody>
        </table>
      </Panel>
    {/each}
  </div>
{/if}

<style>
  .dim { opacity: .6; transition: opacity .15s; }
  .rn { display: inline-flex; align-items: center; gap: 8px; color: var(--ink); max-width: 260px; }
  .rn span:last-child { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .fixed { table-layout: fixed; min-width: 760px; }
  .fixed :global(td) { overflow: hidden; text-overflow: ellipsis; }
  .rn { max-width: 100%; }
  .dirs { color: var(--muted); overflow: hidden; text-overflow: ellipsis; }
  .sk { display: block; height: 10px; width: 60%; border-radius: 2px; background: var(--sunk); }
  .dirs a { color: var(--ink-2); margin-right: 10px; font-size: 12px; }
  .ot { display: inline-flex; align-items: center; gap: 8px; }
  .ot b { width: 36px; text-align: right; font-weight: 650; }
  .bar { width: 44px; height: 8px; background: var(--sunk); display: inline-block; }
  .bar span { display: block; height: 8px; background: var(--ink); }
  .none { color: var(--faint); font-size: 11.5px; }
  input[type="search"] { width: 200px; }
</style>
