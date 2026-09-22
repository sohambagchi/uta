<script lang="ts">
  import { insights } from "../lib/api";
  import { app, load } from "../lib/app.svelte";
  import { router } from "../lib/router.svelte";
  import { clock, dateLabel, delay, dur, pct, lineColor, MINUS, MODE_LABEL, title } from "../lib/format";
  import ScopeBar from "../lib/ui/ScopeBar.svelte";
  import PageTitle from "../lib/ui/PageTitle.svelte";
  import Panel from "../lib/ui/Panel.svelte";
  import Kpi from "../lib/ui/Kpi.svelte";
  import Legend from "../lib/ui/Legend.svelte";
  import RouteBullet from "../lib/ui/RouteBullet.svelte";
  import Maturity from "../lib/ui/Maturity.svelte";
  import Loading from "../lib/ui/Loading.svelte";
  import Tag from "../lib/ui/Tag.svelte";
  import RouteStrip from "../lib/charts/RouteStrip.svelte";
  import RouteHeadways from "../lib/charts/RouteHeadways.svelte";
  import RouteRuntime from "../lib/charts/RouteRuntime.svelte";
  import NBadge from "../lib/ui/NBadge.svelte";
  import DelayCell from "../lib/ui/DelayCell.svelte";

  let { routeId, dir }: { routeId: string; dir: number } = $props();

  const res = load(() => {
    app.tick;
    return insights.route(routeId, dir, { ...router.scopeParams(["from", "to", "dows", "h"]), at: router.get("at") ?? undefined });
  });
  const r = $derived(res.data);
  const color = $derived(r ? lineColor(r.route.route_short_name, r.route.route_color) : "var(--ink)");
  // buses have no line colour of their own: draw them in ink
  const stroke = $derived(r && r.route.mode !== "bus" ? color : "var(--ink)");
  const head = $derived(r?.directions.find((d) => d.direction_id === r.direction_id)?.headsign ?? "");
  const short = (s: string | undefined) => (s ?? "").replace(/ Station$/, "");
  const hwName = $derived(r?.headways ? short(r.stations[r.headways.station]?.name) : "");
  const rtFrom = $derived(r?.runtime.from != null ? short(r.stations[r.runtime.from].name) : "");
  const rtTo = $derived(r?.runtime.to != null ? short(r.stations[r.runtime.to].name) : "");
  const covered = $derived.by(() => {
    if (!r) return 0;
    const ts = r.marey.trips.flatMap((t) => t.obs.map((o) => o[1]));
    return ts.length ? (Math.max(...ts) - Math.min(...ts)) / 3600 : 0;
  });
  const scopeLabel = $derived(r ? (r.scope.from === r.scope.to ? dateLabel(r.scope.to) : `${dateLabel(r.scope.from)} – ${dateLabel(r.scope.to)}`) : "");
  const TABS: [string, string][] = [["overview", "Overview"], ["stops", "Stops"], ["trips", "Trips"], ["headways", "Headways"], ["timetable", "Timetable changes"]];
  const tab = $derived(TABS.some(([k]) => k === router.get("tab")) ? router.get("tab")! : "overview");
  const noRt = $derived(new Set(r?.marey.no_rt ?? []));
  // the Marey day's trips, observed first by first sighting, then the ones never observed
  const tripRows = $derived.by(() => {
    if (!r) return [];
    const obs = r.marey.trips.filter((t) => t.obs.length).map((t) => ({ t, first: t.obs[0], last: t.obs.at(-1)! }))
      .sort((a, b) => a.first[1] - b.first[1]);
    return obs;
  });
  const unseen = $derived(r ? [...r.marey.sched_only].sort((a, b) => (a.sched[0]?.[1] ?? 0) - (b.sched[0]?.[1] ?? 0)) : []);
  const hwStations = $derived(r ? r.stations.map((s, i) => ({ s, i })).filter(({ i }) => r.acc[i].n > 0) : []);
</script>

{#snippet headwayPanel()}
{#if r}
<Panel q="Are vehicles evenly spaced{hwName ? ' at ' + hwName : ''}?" grow n={r.headways?.stats.n ?? 0} nLabel="gaps" warn={(r.headways?.stats.n ?? 0) < 20}
  info="Gap between consecutive arrivals on {dateLabel(r.marey.date)}. Bunched: under ¼ of scheduled. Gap: over 1.5×. A gap spanning an unobserved arrival is excluded: a missing observation is not a missing vehicle.">
  {#snippet right()}
    <select aria-label="Headway station" value={r.headways?.station ?? ""} onchange={(e) => router.set({ at: r.stations[+(e.currentTarget as HTMLSelectElement).value]?.station_id })}>
      {#each hwStations as { s, i }}<option value={i}>{short(s.name)}</option>{/each}
    </select>
  {/snippet}
  {#if r.headways}
    {@const st = r.headways.stats}
    <div class="stats">
      {#each [["Bunched", String(st.bunched)], ["Gaps", String(st.gaps)], ["Excess wait", delay(st.ewt)], ["CV", st.cv != null ? st.cv.toFixed(2) : "—"], ["Not seen", `${st.not_seen} / ${st.scheduled}`]] as [k, v]}
        <div><div class="k">{k}</div><div class="v">{v}</div></div>
      {/each}
    </div>
    <RouteHeadways hw={r.headways} gaps={r.marey.gaps} />
    <Legend items={[{ color: "var(--ink)", label: "observed gap", kind: "dot" }, { color: "var(--faint)", label: "spans an unseen arrival · excluded", kind: "ring" },
      { color: "var(--sched)", label: "scheduled", kind: "dash" }, { color: "var(--sunk)", label: "regular (¼–1.5×)" }, { color: "var(--late-3)", label: "not observed" }]} />
  {:else}
    <Tag kind="hatch">no observed arrivals</Tag>
  {/if}
</Panel>
{/if}
{/snippet}

<ScopeBar show={["dates", "days", "hours", "otp"]} crumbs={r ? [
  ["Network", router.href("network")], [MODE_LABEL[r.route.mode], router.href("routes")],
  [`${r.route.route_short_name} ${title(r.route.route_long_name)}`, null], [head, null]] : [["Routes", router.href("routes")], [routeId, null]]} />

{#if !r}
  <Loading error={res.error} />
{:else}
  <PageTitle title={title(r.route.route_long_name) || r.route.route_short_name} sub="{MODE_LABEL[r.route.mode]} · {r.stations.length} stations · {scopeLabel}{r.feed_version ? ' · feed ' + r.feed_version : ''}">
    {#snippet lead()}<RouteBullet short={r.route.route_short_name} color={r.route.route_color} mode={r.route.mode} size={34} />{/snippet}
    <span class="to">{head ? "to " + head.replace(/^To /, "") : ""}</span>
    {#snippet right()}
      <div class="seg">
        {#each r.directions as d}
          <a class="dir" href={router.href(`routes/${routeId}/${d.direction_id}`, { at: null })} aria-current={d.direction_id === r.direction_id ? "page" : undefined}
            class:on={d.direction_id === r.direction_id}>{d.headsign ?? `Direction ${d.direction_id}`}</a>
        {/each}
      </div>
      <Maturity days={app.days.length} hours={covered} />
    {/snippet}
  </PageTitle>
  <nav class="tabs" aria-label="Route views">
    {#each TABS as [k, label]}
      <a href={router.href(`routes/${routeId}/${dir}`, { tab: k === "overview" ? null : k, at: router.get("at") })}
        class:on={tab === k} aria-current={tab === k ? "page" : undefined}>{label}</a>
    {/each}
  </nav>

  <div class="page" class:dim={res.loading}>
    <div class="kpis">
      <Kpi label="Trips observed" value="{r.kpi.trips_obs} / {r.kpi.trips_sched}" n={r.kpi.trips_sched} warn={false} />
      <Kpi label="On time ({MINUS}1 / +5)" value={pct(r.kpi.otp)} n={r.kpi.n} />
      <Kpi label="Median delay at stops" value={delay(r.kpi.median)} sub="p90 {delay(r.kpi.p90)}" n={r.kpi.n} />
      <Kpi label="End-to-end running time" value={dur(r.kpi.rt_obs)} sub="timetable {dur(r.kpi.rt_sched)}" n={r.kpi.rt_n} warn={r.kpi.rt_n < 20} />
      <Kpi label="Excess wait{hwName ? ' · ' + hwName : ''}" value={delay(r.kpi.ewt)} n={r.kpi.hw_n} warn={r.kpi.hw_n < 20} />
    </div>

    {#if tab === "overview"}
    {#if r.marey.trips.length || r.marey.sched_only.length}
      <Panel q="Where does it lose time?" info="Each line is one trip; steeper is slower. Hover a line for trip, vehicle and delay; click to open the trip. Delay and dwell use the whole scope; the time-space diagram is the last day."
        n={r.kpi.n} nLabel="visits · {r.kpi.trips_obs} trips">
        <RouteStrip {r} color={stroke} />
        <Legend items={[{ color: stroke, label: "observed trip", kind: "line" }, { color: "var(--sched)", label: "timetable", kind: "dash" }, { color: "", label: "no data", kind: "hatch" }]} />
      </Panel>
    {:else}
      <Panel q="Where does it lose time?"><Tag kind="hatch">no trips on {dateLabel(r.marey.date)}</Tag></Panel>
    {/if}

    <div class="row wrap-md">
      {@render headwayPanel()}

      <Panel q="Does the timetable give it enough time?" w={500} cap={rtFrom ? `${rtFrom} → ${rtTo}` : ""} n={r.runtime.trips.length} nLabel="trips"
        warn={r.runtime.trips.length < 20} info="Per trip, by scheduled departure. Only trips observed at both ends count; they are the outermost stations most trips are observed at.">
        {#if r.runtime.trips.length}
          <RouteRuntime trips={r.runtime.trips} gaps={r.marey.gaps} color={stroke} />
          <Legend items={[{ color: stroke, label: "observed", kind: "dot" }, { color: "var(--sched)", label: "trip timetable", kind: "line" }, { color: "var(--sched)", label: "median timetable", kind: "dash" }]} />
        {:else}
          <Tag kind="hatch">no trip observed at both ends</Tag>
        {/if}
      </Panel>
    </div>

    {:else if tab === "stops"}
      <Panel q="How does each stop do?" info="Delay at arrival over the scope: median and p10–p90. Dwell against the timetable's dwell." n={r.kpi.n} nLabel="visits">
        <table class="t">
          <thead><tr><th></th><th>Station</th><th class="r">Visits</th><th class="r">Median delay</th><th class="r">p10 – p90</th><th class="r">Dwell</th><th class="r">Timetable</th></tr></thead>
          <tbody>
            {#each r.stations as st, i}
              {@const a = r.acc[i]}
              <tr class:faint={noRt.has(i)}>
                <td class="mark"><svg width="16" height="30" aria-hidden="true"><line x1="8" x2="8" y1={i === 0 ? 15 : 0} y2={i === r.stations.length - 1 ? 15 : 30} stroke={stroke} stroke-width="4" />
                  <circle cx="8" cy="15" r="3.4" fill="var(--panel)" stroke={stroke} stroke-width="2" stroke-dasharray={noRt.has(i) ? "2 2" : undefined} /></svg></td>
                <td><a href={router.href(`stations/${st.station_id}`)}>{short(st.name)}</a></td>
                {#if noRt.has(i)}
                  <td class="r" colspan="5"><Tag kind="hatch">no realtime</Tag></td>
                {:else}
                  <td class="r"><NBadge n={a.n} warn={a.n < 10} /></td>
                  <td class="r"><DelayCell s={a.median} /></td>
                  <td class="r">{a.n ? `${delay(a.p10)} – ${delay(a.p90)}` : "—"}</td>
                  <td class="r">{dur(a.dwell)}</td>
                  <td class="r muted">{dur(a.sdwell)}</td>
                {/if}
              </tr>
            {/each}
          </tbody>
        </table>
      </Panel>

    {:else if tab === "trips"}
      <Panel q="Which trips ran on {dateLabel(r.marey.date)}?" info="Every trip of this direction on the time-space day. Faint rows are timetabled trips that were never observed."
        n={tripRows.length} nLabel="observed">
        {#snippet right()}{#if unseen.length}<Tag kind="hatch">{unseen.length} not observed</Tag>{/if}{/snippet}
        <table class="t">
          <thead><tr><th>Trip</th><th>Vehicle</th><th>First observed</th><th>Last observed</th><th class="r">Delay at end</th><th class="r">Stops</th></tr></thead>
          <tbody>
            {#each tripRows as { t, first, last } (t.trip_id)}
              <tr>
                <td><a class="mono" href={router.href(`trip/${t.trip_id}`, { date: r.marey.date }, false)}>{t.trip_id}</a></td>
                <td>{#if t.vehicle}<a class="mono" href={router.href(`vehicle/${t.vehicle}`, { date: r.marey.date }, false)}>{t.vehicle}</a>{:else}<span class="muted">—</span>{/if}</td>
                <td><span class="mono">{clock(first[1])}</span> <span class="muted">{short(r.stations[first[0]]?.name)}</span></td>
                <td><span class="mono">{clock(last[1])}</span> <span class="muted">{short(r.stations[last[0]]?.name)}</span></td>
                <td class="r"><DelayCell s={last[2]} /></td>
                <td class="r"><NBadge n={t.obs.length} warn={false} /></td>
              </tr>
            {/each}
            {#each unseen as t (t.trip_id)}
              <tr class="faint">
                <td><a class="mono" href={router.href(`trip/${t.trip_id}`, { date: r.marey.date }, false)}>{t.trip_id}</a></td>
                <td></td>
                <td><span class="mono">{clock(t.sched[0]?.[1])}</span> <span class="muted">{short(r.stations[t.sched[0]?.[0]]?.name)}</span></td>
                <td></td><td class="r" colspan="2"><Tag kind="hatch">not observed</Tag></td>
              </tr>
            {/each}
          </tbody>
        </table>
      </Panel>

    {:else if tab === "headways"}
      {@render headwayPanel()}

    {:else if tab === "timetable"}
      <Panel q="Which timetables has this route run?" info="GTFS feed versions this direction's observed trips came from. Before / after comparisons need a second version.">
        {#snippet right()}{#if r.feeds.length <= 1}<Tag>one timetable so far</Tag>{/if}{/snippet}
        <table class="t">
          <thead><tr><th>Feed version</th><th class="r">Trips</th><th>First day</th><th>Last day</th></tr></thead>
          <tbody>
            {#each r.feeds as f}
              <tr><td class="mono">{f.version}</td><td class="r">{f.trips}</td><td>{f.first ? dateLabel(f.first) : "—"}</td><td>{f.last ? dateLabel(f.last) : "—"}</td></tr>
            {/each}
          </tbody>
        </table>
      </Panel>
    {/if}
  </div>
{/if}

<style>
  .dim { opacity: .6; transition: opacity .15s; }
  .to { color: var(--muted); font-weight: 450; margin-left: .2em; }
  .seg { display: inline-flex; gap: 4px; flex-wrap: wrap; }
  .tabs { display: flex; gap: 22px; margin: 0 20px 14px; border-bottom: 1px solid var(--border); overflow-x: auto; scrollbar-width: none; }
  .tabs a { font-size: 13px; padding: 8px 2px; color: var(--muted); text-decoration: none; white-space: nowrap; }
  .tabs a.on { color: var(--ink); font-weight: 650; box-shadow: inset 0 -2px 0 var(--ink); }
  tr.faint td { color: var(--faint); }
  td.mark { width: 22px; padding: 0 !important; }
  td.mark svg { display: block; }
  @media (max-width: 760px) { .tabs { margin: 0 12px 12px; gap: 16px; } .dir { max-width: 44vw; overflow: hidden; text-overflow: ellipsis; } }
  .dir { height: 30px; padding: 0 12px; border: 1px solid var(--border); background: var(--panel); color: var(--ink-2); font-size: 12.5px;
    border-radius: 4px; white-space: nowrap; display: inline-flex; align-items: center; text-decoration: none; }
  .dir.on { background: var(--ink); color: var(--panel); border-color: var(--ink); font-weight: 600; }
  .stats { display: flex; gap: 28px; flex-wrap: wrap; }
  .stats .k { font-size: 11.5px; color: var(--muted); }
  .stats .v { font-size: 18px; font-weight: 650; }
  select { font-size: 12px; max-width: 200px; }
</style>
