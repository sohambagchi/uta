<script lang="ts">
  import { insights } from "../lib/api";
  import { app, load } from "../lib/app.svelte";
  import { router } from "../lib/router.svelte";
  import { dateLabel, delay, dur, pct, clock, MINUS, MODE_LABEL, title } from "../lib/format";
  import ScopeBar from "../lib/ui/ScopeBar.svelte";
  import PageTitle from "../lib/ui/PageTitle.svelte";
  import Panel from "../lib/ui/Panel.svelte";
  import Kpi from "../lib/ui/Kpi.svelte";
  import NBadge from "../lib/ui/NBadge.svelte";
  import Tag from "../lib/ui/Tag.svelte";
  import Legend from "../lib/ui/Legend.svelte";
  import Sparkline from "../lib/ui/Sparkline.svelte";
  import RouteBullet from "../lib/ui/RouteBullet.svelte";
  import DelayCell from "../lib/ui/DelayCell.svelte";
  import Maturity from "../lib/ui/Maturity.svelte";
  import Loading from "../lib/ui/Loading.svelte";
  import FleetChart from "../lib/charts/FleetChart.svelte";
  import HourHeat from "../lib/charts/HourHeat.svelte";
  import NetMap from "../lib/charts/NetMap.svelte";

  const res = load(() => { app.tick; return insights.network(router.scopeParams()); });
  $effect(() => { app.loadNetwork(); });
  const s = $derived(res.data);
  const MIN_TRIPS = 8;
  const ranked = $derived(s ? s.routes.filter((r) => r.trips >= MIN_TRIPS && r.otp != null) : []);
  const hidden = $derived(s ? s.routes.length - ranked.length : 0);
  const panes = $derived([{ label: "WORST", list: ranked.slice(0, 8) }, { label: "BEST", list: [...ranked].reverse().slice(0, 8) }]);
  const allOtp = $derived(s ? s.hours.map((h) => { const c = s.mode_hour.find((m) => m.mode === "all" && m.h === h); return c && c.n >= 200 ? c.otp : null; }) : []);
  const scopeLabel = $derived(s ? (s.scope.from === s.scope.to ? dateLabel(s.scope.to) : `${dateLabel(s.scope.from)} – ${dateLabel(s.scope.to)} · ${s.scope.days.length} days`) : "");
  const MODE_ROUTE: Record<string, [string, string | null]> = { bus: ["200", null], lrt: ["703", "be2036"], streetcar: ["720", "77777a"], rail: ["750", "c227b9"] };
  const hoursCovered = $derived(s?.fleet.length ? (s.fleet.at(-1)!.t - s.fleet[0].t) / 3600 : 0);
</script>

<ScopeBar crumbs={[["Network", null]]} />
{#if !s}
  <Loading error={res.error} />
{:else}
  <PageTitle title="Network" sub={scopeLabel}>
    {#snippet right()}<Maturity days={app.days.length} hours={hoursCovered} />{/snippet}
  </PageTitle>
  {#if s.kpi.n === 0}
  <div class="page">
    <Panel q="Nothing observed in this scope">
      <div class="row" style="align-items: center; gap: 10px"><Tag kind="hatch">no observed visits</Tag>
        {#if app.latest}<a href={router.href("network", { from: null, to: null, h: null, dows: null, modes: null })}>Latest day →</a>{/if}</div>
    </Panel>
  </div>
  {:else}
  <div class="page" class:dim={res.loading}>
    <div class="kpis">
      <Kpi label="Scheduled trips that ran" value={pct(s.kpi.service.scheduled ? s.kpi.service.observed / s.kpi.service.scheduled : null)}
        sub="{s.kpi.service.observed.toLocaleString()} / {s.kpi.service.scheduled.toLocaleString()} trips" n={s.kpi.service.scheduled} />
      <Kpi label="On time ({MINUS}1 / +5 min)" value={pct(s.kpi.otp)} n={s.kpi.n}>
        {#snippet spark()}<Sparkline vals={allOtp} lo={0.6} hi={1} />{/snippet}
      </Kpi>
      <Kpi label="Median delay" value={delay(s.kpi.median)} sub="p90 {delay(s.kpi.p90)}" n={s.kpi.n} />
      <Kpi label="More than 5 min late" value={pct(s.kpi.late)} sub="early >1 min {pct(s.kpi.early)}" n={s.kpi.n} />
      <Kpi label="Vehicles on a trip" value={s.kpi.vehicles_now?.toString() ?? "—"} sub="timetable {s.kpi.vehicles_sched_now ?? '—'}" n={s.kpi.vehicles_at != null ? clock(s.kpi.vehicles_at) : "—"} warn={false} />
      <Kpi label="Mean dwell" value={dur(s.kpi.dwell_mean)} n={s.kpi.n} />
    </div>

    <div class="row wrap-md">
      <div class="col grow">
        <div class="row wrap-md">
          <Panel q="How punctual is each mode?" info="Share of stop arrivals more than 1 min early, on time (−1 / +5 min) and more than 5 min late, then median delay." w={440}>
            <div>
              {#each s.modes as m}
                {@const o = 1 - (m.early ?? 0) - (m.late ?? 0)}
                <div class="mrow">
                  <span class="mb"><RouteBullet short={MODE_ROUTE[m.mode][0]} color={MODE_ROUTE[m.mode][1]} mode={m.mode} size={20} /></span>
                  <span class="ml">{MODE_LABEL[m.mode]}</span>
                  <span class="stack" title="{pct(m.early)} early · {pct(o)} on time · {pct(m.late)} late">
                    <span style:width="{(m.early ?? 0) * 100}%" style:background="var(--early)"></span>
                    <span style:width="{o * 100}%" style:background="var(--ontime)"></span>
                    <span style:width="{(m.late ?? 0) * 100}%" style:background="var(--late-3)"></span>
                  </span>
                  <b class="mv">{pct(o, 0)}</b><span class="md">{delay(m.median)}</span>
                  <span class="mn"><NBadge n={m.n} /></span>
                </div>
              {/each}
            </div>
            <Legend items={[{ color: "var(--early)", label: "early >1 min" }, { color: "var(--ontime)", label: "on time" }, { color: "var(--late-3)", label: "late >5 min" }]} />
          </Panel>
          <Panel q="When is service latest?" info="Median delay at stops in minutes, by hour of arrival. Hatched: fewer than 15 visits." grow>
            <HourHeat cells={s.mode_hour} hours={s.hours} modes={s.modes.map((m) => m.mode)} />
            <Legend delay items={[{ color: "", label: "under 15 visits", kind: "hatch" }]} />
          </Panel>
        </div>

        <Panel q="Which routes are running worst and best?" info="Ranked by on-time share at stops (−1 / +5 min). Routes with fewer than {MIN_TRIPS} observed trips are not ranked.">
          {#snippet right()}{#if hidden}<Tag>{hidden} routes &lt; {MIN_TRIPS} trips hidden</Tag>{/if}{/snippet}
          <div class="panes">
            {#each panes as { label, list }}
              <div class="grow tw">
                <div class="rank" class:worst={label === "WORST"}>{label} 8</div>
                <table class="t">
                  <thead><tr><th>Route</th><th>On time</th><th class="r">Median</th><th>By hour</th><th class="r">Trips</th></tr></thead>
                  <tbody>
                    {#each list as r (r.route_id)}
                      <tr class="link" onclick={() => router.go(`routes/${r.route_id}/0`)}>
                        <td><a class="rn" href={router.href(`routes/${r.route_id}/0`)}><RouteBullet short={r.short} color={r.color} mode={r.mode} size={20} /><span>{title(r.long)}</span></a></td>
                        <td><span class="ot"><span class="bar"><span style:width="{(r.otp ?? 0) * 100}%"></span></span><b>{pct(r.otp, 0)}</b></span></td>
                        <td class="r"><DelayCell s={r.median} /></td>
                        <td><Sparkline vals={r.spark} w={50} h={18} lo={0.3} hi={1} /></td>
                        <td class="r mono">{r.trips}</td>
                      </tr>
                    {/each}
                  </tbody>
                </table>
              </div>
            {/each}
          </div>
        </Panel>

        {#if s.fleet.length}
          <Panel q="How many vehicles were out, versus the timetable?" info="Vehicles reporting a trip (GPS) vs trips the timetable has running, every 10 minutes, on the last day of the range." cap={s.scope.from !== s.scope.to ? dateLabel(s.scope.to) : undefined} n={s.fleet.length * 10} nLabel="min">
            <FleetChart fleet={s.fleet} gaps={s.gaps} />
            <Legend items={[{ color: "var(--ink)", label: "observed", kind: "line" }, { color: "var(--sched)", label: "timetable", kind: "dash" }, { color: "", label: "no data", kind: "hatch" }]} />
          </Panel>
        {/if}
      </div>

      <Panel q="Where is delay generated?" info="Median delay at stations with 15+ observed visits, sized by visits. Lines are grey so delay owns the colour. Click a station to open it." n={s.stations.filter((x) => x.n >= 15).length} nLabel="stations" w={460}>
        <NetMap lines={app.lines} rail={app.rail} stations={s.stations} />
        <Legend delay />
        <Legend items={[{ color: "var(--ink-2)", label: "size = visits", kind: "dot" }, { color: "var(--axis)", label: "rail", kind: "line" }, { color: "var(--grid)", label: "bus", kind: "line" }]} />
      </Panel>
    </div>
  </div>
  {/if}
{/if}

<style>
  .dim { opacity: .6; transition: opacity .15s; }
  .mrow { display: flex; align-items: center; gap: 10px; height: 34px; border-bottom: 1px solid var(--grid); }
  .mb { width: 34px; display: flex; }
  .ml { width: 88px; font-weight: 550; }
  .stack { display: flex; flex: 1; height: 14px; border-radius: 2px; overflow: hidden; min-width: 80px; }
  .mv { width: 42px; text-align: right; font-weight: 650; }
  .md { width: 48px; text-align: right; color: var(--ink-2); }
  .mn { width: 78px; text-align: right; }
  .panes { display: grid; grid-template-columns: repeat(auto-fit, minmax(400px, 1fr)); gap: 16px 24px; }
  @media (max-width: 480px) { .panes { grid-template-columns: minmax(0, 1fr); } }
  .tw :global(table.t td), .tw :global(table.t th) { padding: 0 5px; }
  .rank { font-size: 12px; font-weight: 650; color: var(--ink-2); margin-bottom: 6px; }
  .rank.worst { color: var(--late-3); }
  .rn { display: inline-flex; align-items: center; gap: 8px; color: var(--ink); max-width: 150px; }
  .rn span:last-child { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .ot { display: inline-flex; align-items: center; gap: 8px; }
  .ot b { width: 36px; text-align: right; font-weight: 650; }
  .bar { width: 34px; height: 8px; background: var(--sunk); display: inline-block; }
  .bar span { display: block; height: 8px; background: var(--ink); }
</style>
