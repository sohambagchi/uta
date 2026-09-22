<script lang="ts">
  import { insights } from "../lib/api";
  import { app, load } from "../lib/app.svelte";
  import { router } from "../lib/router.svelte";
  import { clock, dateLabel, delay, dur, lineColor, title, MINUS } from "../lib/format";
  import ScopeBar from "../lib/ui/ScopeBar.svelte";
  import PageTitle from "../lib/ui/PageTitle.svelte";
  import Panel from "../lib/ui/Panel.svelte";
  import Kpi from "../lib/ui/Kpi.svelte";
  import Tag from "../lib/ui/Tag.svelte";
  import Legend from "../lib/ui/Legend.svelte";
  import RouteBullet from "../lib/ui/RouteBullet.svelte";
  import DelayCell from "../lib/ui/DelayCell.svelte";
  import Loading from "../lib/ui/Loading.svelte";
  import TripDelayProfile from "../lib/charts/TripDelayProfile.svelte";
  import TripGps from "../lib/charts/TripGps.svelte";
  import TripSpeed from "../lib/charts/TripSpeed.svelte";

  let { tripId }: { tripId: string } = $props();
  const res = load(() => { app.tick; return insights.trip(tripId, router.get("date") ?? undefined); });
  const v = $derived(res.data);
  const color = $derived(v ? lineColor(v.trip.short, v.trip.color) : "var(--ink)");
  const obs = $derived(v ? v.stops.filter((s) => s.observed && s.delay != null) : []);
  const first = $derived(obs[0]);
  const last = $derived(obs.at(-1));
  const worst = $derived(obs.length ? obs.reduce((a, b) => (b.delay! > a.delay! ? b : a)) : undefined);
  const dwell = $derived(obs.reduce((a, s) => a + (s.dwell ?? 0), 0));
  const sdwell = $derived(obs.reduce((a, s) => a + (s.sdwell ?? 0), 0));
  const run = $derived(first && last && first !== last ? last.obs! - first.obs! : null);
  const srun = $derived(first && last && first !== last && first.sched != null && last.sched != null ? last.sched - first.sched : null);
  const blockIdx = $derived(v ? v.block_trips.findIndex((b) => b.trip_id === v.trip.trip_id) : -1);
  const prev = $derived(v && blockIdx > 0 ? v.block_trips[blockIdx - 1] : null);
  const next = $derived(v && blockIdx >= 0 && blockIdx < v.block_trips.length - 1 ? v.block_trips[blockIdx + 1] : null);
  const half = $derived(v ? Math.ceil(v.stops.length / 2) : 0);
  const halves = $derived(v ? [v.stops.slice(0, half), v.stops.slice(half)] : []);
  const unseen = $derived(v ? v.stops.filter((s) => !s.observed).length : 0);
  const short = (n: string | null) => (n ?? "—").replace(/ Station$/, "");
  $effect(() => { app.loadNetwork(); });
</script>

<ScopeBar crumbs={[["Trips & vehicles", router.href("trips")], ...(v?.trip.block_id ? [["Block " + v.trip.block_id, null] as [string, null]] : []), ["Trip " + tripId, null]]} show={[]}>
  {#snippet extra()}
    {#if v}
      <label class="dt"><span class="lab">Date</span>
        <select aria-label="Service date" value={v.trip.date} disabled={v.days.length < 2}
          onchange={(e) => router.set({ date: (e.currentTarget as HTMLSelectElement).value })}>
          {#each v.days.includes(v.trip.date) ? v.days : [...v.days, v.trip.date] as d}<option value={d}>{dateLabel(d)}</option>{/each}
        </select>
      </label>
    {/if}
  {/snippet}
</ScopeBar>
{#if !v}
  <Loading error={res.error} />
{:else}
  <PageTitle title="Trip {v.trip.trip_id}" sub="{dateLabel(v.trip.date)}{v.stops[0]?.sched != null ? ` · scheduled ${clock(v.stops[0].sched)} from ${short(v.stops[0].name)}` : ''}">
    {#snippet lead()}<RouteBullet short={v.trip.short} color={v.trip.color} mode={v.trip.mode} size={34} />{/snippet}
    <span class="hs">{v.trip.short} {title(v.trip.long)} · {v.trip.headsign ?? ""}</span>
    {#snippet right()}
      {#each v.vehicles as veh}<a class="chip mono" href={router.href(`vehicle/${veh.vehicle_id}`, { date: v.trip.date })}>{veh.vehicle_id}</a>{/each}
      {#if v.trip.block_id}<Tag>block {v.trip.block_id}</Tag>{/if}
      {#if prev}<a class="chip" href={router.href(`trip/${prev.trip_id}`, { date: v.trip.date })}>◀ Previous trip on block <span class="muted mono">{clock(prev.start)}</span></a>{/if}
      {#if next}<a class="chip" href={router.href(`trip/${next.trip_id}`, { date: v.trip.date })}>Next trip on block <span class="muted mono">{clock(next.start)}</span> ▶</a>{/if}
    {/snippet}
  </PageTitle>
  <div class="page" class:dim={res.loading}>
    <div class="kpis">
      <Kpi label="First observed stop" value={delay(first?.delay)} sub={short(first?.name ?? null)} n="1 stop" warn={false} />
      <Kpi label="Worst delay" value={delay(worst?.delay)} sub={short(worst?.name ?? null)} n={obs.length} warn={false} />
      <Kpi label="Last observed stop" value={delay(last?.delay)} sub={short(last?.name ?? null)} n="1 stop" warn={false} />
      <Kpi label="Total dwell" value={dur(dwell)} sub="timetable {dur(sdwell)}" n={obs.length} warn={false} />
      <Kpi label="Running time, observed stops" value={dur(run)} sub="timetable {dur(srun)}" n={obs.length} warn={false} />
    </div>
    {#if !obs.length}<div><Tag kind="warn">not observed on {dateLabel(v.trip.date)}</Tag></div>{/if}

    <div class="row wrap-md">
      <div class="col grow">
        <Panel q="Where did this trip gain and lose time?" info="Observed arrival minus timetable at each stop. Hover a point for times.">
          <TripDelayProfile stops={v.stops} {color} />
          <Legend delay items={[{ color, label: "delay at arrival", kind: "line" }]} />
        </Panel>
        <Panel q="How fast was it moving?" info="GPS speed of the vehicle; dotted verticals are observed stop arrivals. Pings every 30 s undercount short stops." n={v.gps.length} nLabel="pings" warn={false}>
          {#if v.gps.length > 1}<TripSpeed gps={v.gps} stops={v.stops} {color} />{:else}<Tag kind="hatch">no GPS</Tag>{/if}
        </Panel>
      </div>
      <Panel q="Where was it, ping by ping?" info="GPS every 30 s, coloured by speed; circles are stops (grey: not observed)." n={v.gps.length} nLabel="pings" warn={false} w={472}>
        <TripGps gps={v.gps} stops={v.stops} context={app.lines} />
        <Legend items={[{ color: "var(--late-3)", label: "< 3 m/s" }, { color: "var(--late-1)", label: "3–10" }, { color: "var(--ink-2)", label: "10–18" }, { color: "var(--early)", label: "> 18 m/s" }]} />
      </Panel>
    </div>

    <Panel q="Stop by stop" info="Lead = observed arrival minus the last prediction; a visit counts as observed when lead is between −120 and +15 s. Faint rows have no observed time.">
      {#snippet right()}<Tag>{v.stops.length - unseen} / {v.stops.length} observed</Tag>{#if unseen}<Tag kind="hatch">{unseen} no realtime</Tag>{/if}{/snippet}
      <div class="halves">
        {#each halves as part}
          <div class="grow">
            <table class="t">
              <thead><tr><th>Stop</th><th>Sched</th><th>Arrived</th><th class="r">Delay</th><th class="r">Dwell</th><th class="r">Lead</th></tr></thead>
              <tbody>
                {#each part as s (s.seq)}
                  <tr class:faint={!s.observed}>
                    <td class="nm">{#if s.station_id}<a href={router.href(`stations/${s.station_id}`)}>{short(s.name)}</a>{:else}{short(s.name)}{/if}</td>
                    <td class="mono">{clock(s.sched)}</td>
                    <td class="mono">{s.observed ? clock(s.obs, true) : "—"}</td>
                    <td class="r">{#if s.observed}<DelayCell s={s.delay} />{:else}—{/if}</td>
                    <td class="r">{s.observed ? dur(s.dwell) : "—"}</td>
                    <td class="r mono muted">{s.lead != null ? `${s.lead > 0 ? "+" : s.lead < 0 ? MINUS : ""}${Math.abs(s.lead)} s` : "—"}</td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        {/each}
      </div>
    </Panel>
  </div>
{/if}

<style>
  .dt { display: flex; align-items: center; gap: 4px; }
  .lab { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: .06em; font-weight: 600; font-stretch: 90%; margin-right: 3px; }
  .dim { opacity: .6; transition: opacity .15s; }
  .hs { font-size: 20px; color: var(--muted); font-weight: 450; margin-left: 8px; }
  .nm { max-width: 200px; overflow: hidden; text-overflow: ellipsis; }
  .nm a { color: var(--ink); }
  tr.faint td, tr.faint td a { color: var(--faint); }
  a.chip { text-decoration: none; }
  .halves { display: grid; grid-template-columns: repeat(auto-fit, minmax(470px, 1fr)); gap: 0 24px; }
  @media (max-width: 560px) { .halves { grid-template-columns: minmax(0, 1fr); } }
</style>
