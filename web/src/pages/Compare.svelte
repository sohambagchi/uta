<script lang="ts">
  // Segment comparison A–D: up to four stretches (route, direction, From → To) side by side.
  // State (comparisons and filters) lives in the #/compare?… query via the store.
  import { onMount } from "svelte";
  import { store, MAX_COMPARISONS } from "../lib/store.svelte";
  import { router } from "../lib/router.svelte";
  import { buildSeries, type Series } from "../lib/series";
  import MapView from "../lib/MapView.svelte";
  import ScopeBar from "../lib/ui/ScopeBar.svelte";
  import Panel from "../lib/ui/Panel.svelte";
  import Legend from "../lib/ui/Legend.svelte";
  import Info from "../lib/ui/Info.svelte";
  import Tag from "../lib/ui/Tag.svelte";
  import SlotCard from "../lib/compare/SlotCard.svelte";
  import StopStrip from "../lib/compare/StopStrip.svelte";
  import CompareFilters from "../lib/compare/CompareFilters.svelte";
  import StatsTable from "../lib/compare/StatsTable.svelte";
  import TodCell from "../lib/compare/TodCell.svelte";
  import Ecdf from "../lib/compare/Ecdf.svelte";
  import BoxStrip from "../lib/compare/BoxStrip.svelte";
  import HourLines from "../lib/compare/HourLines.svelte";
  import Weekday from "../lib/compare/Weekday.svelte";
  import Daily from "../lib/compare/Daily.svelte";
  import RecentTrips from "../lib/compare/RecentTrips.svelte";
  import { durDomain, hourDomain, tickDur, tickSigned } from "../lib/compare/util";
  import { schedBins } from "../lib/chartdata";

  let ready = $state(false);

  onMount(() => {
    store.fromHash(router.route.query.toString());
    store.loadRoutes().then(() => (ready = true));
  });

  // fetch segments for complete comparisons
  $effect(() => {
    for (const c of store.comparisons) if (store.segmentKey(c)) store.loadSegment(c);
  });

  // keep the URL in sync without adding history entries
  $effect(() => {
    const h = store.toHash();
    if (ready) history.replaceState(null, "", "#/compare" + (h ? "?" + h : ""));
  });

  const series = $derived.by(() => {
    const out: Series[] = [];
    for (const c of store.comparisons) {
      const data = store.segmentData(c);
      if (!data || !(c.from && c.to)) continue;
      const r = store.routeById.get(data.route_id);
      out.push(buildSeries(c, data, r?.route_short_name ?? data.route_id, store.filters));
    }
    return out;
  });
  const bySlot = $derived(new Map(series.map((s) => [s.c.id, s])));
  const loading = $derived(store.comparisons.some((c) => store.segment(c)?.status === "loading"));
  const active = $derived(series.find((s) => s.c.id === store.activeId) ?? series[0]);
  const withTrips = $derived(series.filter((s) => s.trips.length));
  const trimmed = $derived(series.reduce((a, s) => a + s.trimmed, 0));
  const nextSlot = $derived([0, 1, 2, 3].find((k) => !store.comparisons.some((c) => c.slot === k)) ?? 3);

  // shared axes for the small multiples: observed hours (timetable only when nothing was observed)
  const bin = $derived(store.filters.bin);
  const xdom = $derived.by(() => {
    const obs = series.flatMap((s) => s.trips.map((t) => t.minute));
    if (obs.length) return hourDomain(obs);
    return hourDomain(series.flatMap((s) => s.sched.map((r) => r.minute)));
  });
  const ydom = $derived(durDomain([
    ...series.flatMap((s) => s.trips.map((t) => t.dur)),
    ...series.flatMap((s) => schedBins(s, bin).filter((p) => p.x >= xdom[0] && p.x <= xdom[1]).map((p) => p.median * 60)),
  ]));

  const crumbs = $derived.by((): [string, string | null][] => {
    const s = active;
    return s ? [["Compare", "#/compare"], [`${s.seg.from.name.replace(/ Station$/, "")} → ${s.seg.to.name.replace(/ Station$/, "")}`, null]] : [["Compare", null]];
  });
</script>

<ScopeBar {crumbs} show={["otp"]} />
<div class="layout">
  <aside class="side">
    <div class="head">
      <span class="lbl">COMPARISONS · {store.comparisons.length} OF {MAX_COMPARISONS}</span>
    </div>
    {#if ready}
      <div class="cards">
        {#each store.comparisons as c (c.id)}<SlotCard {c} s={bySlot.get(c.id)} />{/each}
        {#if store.comparisons.length < MAX_COMPARISONS}
          <button class="add" style:--c="var(--slot-{nextSlot + 1})" onclick={() => store.add()}>
            <span class="ghost">{"ABCD"[nextSlot]}</span><span>Add comparison</span><span class="plus" aria-hidden="true">+</span>
          </button>
        {/if}
      </div>
      {#if store.active}<StopStrip c={store.active} />{/if}
    {:else}
      <div class="cards"><Tag>loading routes…</Tag></div>
    {/if}
  </aside>

  <div class="main">
    <div class="map"><MapView /></div>
    <div class="page body" class:dim={loading}>
      <CompareFilters {trimmed} />

      {#if !series.length}
        <section class="empty">
          {#each ["Pick a route", "Tap two stops", "Add up to four"] as step, i}
            <div class="step"><span class="num" style:--c="var(--slot-{i + 1})">{i + 1}</span><b>{step}</b></div>
          {/each}
          <span class="sp"></span>
          <Info text="Each comparison times one stretch of one route: from leaving the first stop to arriving at the second. Pick the stops on the strip map on the left or on the map. Same stops on different routes, or different stretches of one route." />
        </section>
      {:else}
        <StatsTable {series} />

        <Panel q="Does it take longer at some times of day?"
          info="Every trip as a dot by departure time; the line is the median per bin and the band p10–p90, drawn only where a bin has 3 or more trips. Dashed: timetable. Shared axes across slots.">
          <div class="mult">
            {#each series as s (s.c.id)}<TodCell {s} {bin} {xdom} {ydom} />{/each}
          </div>
          <Legend items={[{ color: "var(--ink-2)", label: "trip", kind: "dot" }, { color: "var(--ink-2)", label: "median", kind: "line" },
            { color: "var(--sched)", label: "timetable", kind: "dash" }]} />
        </Panel>

        {#if withTrips.length}
          <div class="row wrap-md">
            <Panel q="How likely is each to make it in time?" info="Cumulative share of trips taking at most x. Steeper is more predictable, further left is faster. Dashed: timetable." grow>
              <Ecdf series={withTrips} />
            </Panel>
            <Panel q="What does the spread look like?" info="Box p25–p75, tick median, whiskers min–max, dots every trip (hover for time and vehicle). Dashed tick: timetable." grow>
              <BoxStrip series={withTrips} />
            </Panel>
          </div>
          <div class="row wrap-md">
            <Panel q="How predictable is it through the day?" info="Spread between the fastest and slowest tenth of trips (p90 − p10) per time bin with 3+ trips. Higher is less predictable." grow>
              <HourLines series={withTrips} {bin} field="spread" {xdom} fmt={tickDur} />
            </Panel>
            <Panel q="Is it keeping to the timetable?" info="Median of each trip's observed minus timetabled time, per time bin with 3+ trips. Above zero is slower than timetabled." grow>
              <HourLines series={withTrips} {bin} field="vsSched" {xdom} fmt={tickSigned} />
            </Panel>
          </div>
          <div class="row wrap-md">
            <Panel q="Is it slower on some days of the week?" info="Median per weekday (dot) and middle half (line). Until a weekday has 3 service days of history this shows progress instead." grow>
              <Weekday series={withTrips} />
            </Panel>
            <Panel q="Day by day" info="Median per service day." grow>
              <Daily series={withTrips} />
            </Panel>
          </div>
        {/if}

        {#if active}<RecentTrips s={active} />{/if}
      {/if}
    </div>
  </div>
</div>

<style>
  .layout { display: grid; grid-template-columns: 360px minmax(0, 1fr); align-items: start; }
  .side { border-right: 1px solid var(--border); background: var(--page); position: sticky; top: var(--header-h);
    max-height: calc(100vh - var(--header-h)); overflow: auto; }
  .head { padding: 14px 16px 8px; }
  .lbl { font-size: 11px; font-weight: 650; color: var(--muted); letter-spacing: .06em; }
  .cards { padding: 0 16px; display: flex; flex-direction: column; gap: 10px; }
  .add { display: flex; align-items: center; gap: 10px; height: 44px; padding: 0 12px; border: 1.5px dashed var(--axis); border-radius: 6px;
    background: none; color: var(--ink-2); font-weight: 600; font-size: 12.5px; text-align: left; }
  .add:hover { border-color: var(--c); color: var(--ink); }
  .ghost { width: 24px; height: 24px; border-radius: 50%; border: 1.5px dashed var(--c); color: var(--c); display: inline-grid;
    place-items: center; font-weight: 750; font-size: 12px; }
  .plus { margin-left: auto; font-size: 18px; color: var(--muted); }
  .main { min-width: 0; }
  .map { height: 320px; position: relative; border-bottom: 1px solid var(--border); }
  .body { padding-top: 16px; }
  .dim { opacity: .6; transition: opacity .15s; }
  .empty { display: flex; align-items: center; gap: 24px; background: var(--panel); border: 1px solid var(--border); border-radius: 6px;
    padding: 16px 18px; flex-wrap: wrap; }
  .step { display: flex; align-items: center; gap: 10px; font-size: 14px; }
  .step b { font-weight: 650; }
  .num { width: 26px; height: 26px; border-radius: 50%; background: var(--c); color: #fff; display: inline-grid; place-items: center;
    font-weight: 750; font-size: 13px; }
  .sp { flex: 1; }
  .mult { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 280px), 1fr)); gap: 12px 20px; }
  @media (max-width: 900px) {
    .layout { display: block; }
    .side { position: static; max-height: none; border-right: 0; border-bottom: 1px solid var(--border); }
    .side :global(ol) { max-height: 50vh; overflow: auto; }
  }
</style>
