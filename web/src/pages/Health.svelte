<script lang="ts">
  import { insights } from "../lib/api";
  import { app, load } from "../lib/app.svelte";
  import { router } from "../lib/router.svelte";
  import { epochClock, pct, n } from "../lib/format";
  import ScopeBar from "../lib/ui/ScopeBar.svelte";
  import PageTitle from "../lib/ui/PageTitle.svelte";
  import Panel from "../lib/ui/Panel.svelte";
  import Kpi from "../lib/ui/Kpi.svelte";
  import Tag from "../lib/ui/Tag.svelte";
  import Legend from "../lib/ui/Legend.svelte";
  import RouteBullet from "../lib/ui/RouteBullet.svelte";
  import Maturity from "../lib/ui/Maturity.svelte";
  import Loading from "../lib/ui/Loading.svelte";
  import HealthPolls from "../lib/charts/HealthPolls.svelte";

  const res = load(() => { app.tick; return insights.health(router.scopeParams(["from", "to"])); });
  const h = $derived(res.data);
  const k = $derived(h?.kpi);
  const hours = $derived(h ? h.kpi.span_s / 3600 : 0);
  const DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  const steps = $derived(h ? [
    { label: `Now · ${h.maturity.days} ${h.maturity.days === 1 ? "day" : "days"}`, what: "summaries · every trip · Marey", on: true },
    { label: "3 days", what: "time-of-day bands", on: h.maturity.days >= 3 },
    { label: "3 weeks", what: "day of week · calendar", on: h.maturity.days >= 21 },
    { label: "Next timetable", what: "before / after", on: false },
  ] : []);
  const offlineMin = $derived(k ? Math.round(k.offline_s / 60) : 0);
</script>

<ScopeBar crumbs={[["Data health", null]]} show={["dates"]} />
{#if !h || !k}
  <Loading error={res.error} />
{:else}
  <PageTitle title="Data health" sub="Collector · feed · coverage">
    {#snippet right()}<Maturity days={h.maturity.days} hours={hours} />{/snippet}
  </PageTitle>
  <div class="page" class:dim={res.loading}>
    <div class="kpis">
      <Kpi label="Last poll" value={k.last_poll ? epochClock(k.last_poll) : "—"} sub="every 10 s" n={k.polls} />
      <Kpi label="Collector uptime" value={pct(k.uptime, 0)} sub={offlineMin ? `${offlineMin} min offline` : "no gaps"}
        n={`${Math.floor(k.span_s / 3600)} h ${Math.round((k.span_s % 3600) / 60)} m`} warn={false} />
      <Kpi label="Feed lag" value={k.lag_median != null ? `${Math.round(k.lag_median)} s` : "—"} sub="median · max {k.lag_max ?? '—'} s" n={k.polls} warn={false} />
      <Kpi label="Poll errors" value={n(k.errors)} sub={k.error_kinds[0]?.[0] ?? "none"}
        n={k.polls ? pct(k.errors / k.polls) : "—"} warn={false} />
      <Kpi label="Visits counted as observed" value={pct(k.visits ? k.observed / k.visits : null)}
        sub="{n(k.rejected)} outside lead window" n={k.visits} />
    </div>

    <Panel q="Did the collector keep up?" info="One tick per poll; errors in red. Polls that returned an empty snapshot are gaps, not zeros. Long ranges are shown as per-interval medians." n={k.polls} nLabel="polls">
      {#if h.series.ts.length}
        <HealthPolls series={h.series} gaps={h.gaps} />
      {:else}
        <Tag kind="warn">no polls in range</Tag>
      {/if}
      <Legend items={[{ color: "var(--axis)", label: "poll" }, { color: "var(--late-3)", label: "error" }, { color: "", label: "no polls", kind: "hatch" }]} />
    </Panel>

    <div class="row wrap-md">
      <Panel q="Which routes are we seeing least of?" grow
        info="Scheduled stop visits outside collector gaps vs visits the collector recorded, lowest share first. UTA publishes no realtime for first stops; the rest of the shortfall is not yet explained.">
        {#snippet right()}
          {#if h.network_share != null}<span class="net"><span class="muted">network</span><b>{pct(h.network_share, 0)}</b></span>{/if}
          <Tag kind="warn">open question</Tag>
        {/snippet}
        {#if h.coverage.length}
          <table class="t">
            <thead><tr><th>Route</th><th class="r">Scheduled</th><th class="r">Recorded</th><th>Recorded share</th><th class="r">Observed</th><th class="r">First stops</th></tr></thead>
            <tbody>
              {#each h.coverage.slice(0, 14) as c (c.route_id)}
                <tr class="link" onclick={() => router.go(`routes/${c.route_id}/0`)}>
                  <td><a href={router.href(`routes/${c.route_id}/0`)}><RouteBullet short={c.short} color={c.color} mode={c.mode} size={20} /></a></td>
                  <td class="r mono">{n(c.sched)}</td>
                  <td class="r mono">{n(c.recorded)}</td>
                  <td><span class="sh"><span class="bar"><span style:width="{Math.min(1, c.share) * 100}%" style:background={c.share < 0.5 ? "var(--late-3)" : "var(--ink)"}></span></span><b>{pct(c.share, 0)}</b></span></td>
                  <td class="r">{pct(c.recorded ? c.observed / c.recorded : null, 0)}</td>
                  <td class="r mono">{n(c.first)}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        {:else}
          <Tag>no scheduled visits in range</Tag>
        {/if}
      </Panel>

      <Panel q="How much history backs the views?" w={420}
        info="Time-of-day bands need 3+ trips per bin (about 3 days); weekday comparisons need 3 of each weekday (about 3 weeks).">
        <div class="steps">
          {#each steps as s}
            <div class="st"><span class="node" class:on={s.on}></span><div><b>{s.label}</b><div class="w" class:on={s.on}>{s.what}</div></div></div>
          {/each}
        </div>
        <div class="dows">
          {#each DOW as d, i}
            {@const c = h.maturity.by_dow[i] ?? 0}
            <div class="dw"><span class="dl">{d}</span>
              <span class="segs">{#each [0, 1, 2] as j}<span class:on={c > j}></span>{/each}</span>
              <span class="dn mono">{c}/3</span></div>
          {/each}
        </div>
      </Panel>
    </div>
  </div>
{/if}

<style>
  .dim { opacity: .6; transition: opacity .15s; }
  .net { display: inline-flex; gap: 6px; align-items: baseline; font-size: 11.5px; }
  .net b { font-size: 16px; }
  .sh { display: inline-flex; align-items: center; gap: 8px; }
  .sh b { width: 38px; text-align: right; font-weight: 650; }
  .bar { width: 90px; height: 8px; background: var(--sunk); display: inline-block; }
  .bar span { display: block; height: 8px; }
  .steps { display: flex; flex-direction: column; gap: 12px; }
  .st { display: flex; gap: 12px; align-items: flex-start; font-size: 13px; }
  .node { width: 12px; height: 12px; border-radius: 50%; border: 2px solid var(--axis); margin-top: 3px; flex: none; }
  .node.on { background: var(--ink); border-color: var(--ink); }
  .w { font-size: 12px; color: var(--muted); }
  .w.on { color: var(--ink-2); }
  .dows { display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); gap: 6px; margin-top: 6px; }
  .dw { display: flex; flex-direction: column; gap: 4px; }
  .dl { font-size: 11px; font-weight: 600; color: var(--ink-2); }
  .segs { display: flex; gap: 2px; }
  .segs span { flex: 1; height: 10px; border-radius: 1px; background: var(--sunk); }
  .segs span.on { background: var(--ink); }
  .dn { font-size: 10.5px; color: var(--muted); }
</style>
