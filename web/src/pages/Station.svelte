<script lang="ts">
  import { insights, type Mode, type StationView } from "../lib/api";
  import { app, load } from "../lib/app.svelte";
  import { router } from "../lib/router.svelte";
  import { clock, dateLabel, dur, pct, MODE_LABEL } from "../lib/format";
  import ScopeBar from "../lib/ui/ScopeBar.svelte";
  import PageTitle from "../lib/ui/PageTitle.svelte";
  import Panel from "../lib/ui/Panel.svelte";
  import NBadge from "../lib/ui/NBadge.svelte";
  import Tag from "../lib/ui/Tag.svelte";
  import Legend from "../lib/ui/Legend.svelte";
  import RouteBullet from "../lib/ui/RouteBullet.svelte";
  import DelayCell from "../lib/ui/DelayCell.svelte";
  import Maturity from "../lib/ui/Maturity.svelte";
  import Loading from "../lib/ui/Loading.svelte";
  import StationArrivals from "../lib/charts/StationArrivals.svelte";
  import StationTransfer from "../lib/charts/StationTransfer.svelte";

  let { stationId }: { stationId: string } = $props();

  const res = load(() => {
    app.tick;
    return insights.station(stationId, {
      ...router.scopeParams(["from", "to", "dows", "h"]),
      until: router.get("until") ?? undefined, xf: router.get("xf") ?? undefined, xt: router.get("xt") ?? undefined,
    });
  });
  const s = $derived(res.data);
  const name = $derived(s ? s.station.name.replace(/ Station$/, "") : "");
  // mode identity, kept clear of the delay palette's grey
  const MODE_COLOR: Record<Mode, string> = { lrt: "var(--ink)", streetcar: "var(--line-720)", rail: "var(--line-750)", bus: "var(--muted)" };

  // platforms grouped by the routes they serve; bays one box each
  type Box = { key: string; label: string; stops: number; routes: StationView["served"]; sched: number; observed: number; terminal: boolean; bay: boolean };
  const boxes = $derived.by((): Box[] => {
    if (!s) return [];
    const out: Box[] = [];
    const plat = new Map<string, Box>();
    for (const st of s.stops) {
      if (st.bay) {
        out.push({ key: st.stop_id, label: st.bay, stops: 1, routes: st.routes, sched: st.sched, observed: st.observed, terminal: st.terminal_only, bay: true });
        continue;
      }
      const k = st.routes.map((r) => r.route_id).join(",");
      const b = plat.get(k);
      if (b) { b.sched += st.sched; b.observed += st.observed; b.terminal &&= st.terminal_only; b.stops++; }
      else plat.set(k, { key: k || st.stop_id, label: st.routes.length ? MODE_LABEL[st.routes[0].mode] : "Stop", stops: 1, routes: st.routes, sched: st.sched,
        observed: st.observed, terminal: st.terminal_only, bay: false });
    }
    return [...plat.values(), ...out];
  });

  const until = $derived(s?.board_until ?? 0);
  const lastObs = $derived(s?.board.at(-1)?.obs ?? 0);
  function earlier() { router.set({ until: Math.max(0, until - 1800) }); }
  function later() { const v = until + 1800; router.set({ until: s && v >= (s.hours.at(-1)?.h ?? 0) * 3600 + 3600 ? null : v }); }

  const xfer = $derived(s?.xfer ?? null);
  // only connections while the collector was polling (hours with arrivals, minus gaps)
  const polled = $derived.by(() => {
    if (!s || !s.hours.length) return () => false;
    const lo = s.hours[0].h * 3600, hi = (s.hours.at(-1)!.h + 1) * 3600;
    return (t: number) => t >= lo && t < hi && !s.gaps.some(([a, b]) => t >= a && t <= b);
  });
  const xall = $derived(xfer ? xfer.events.filter((e) => polled(e.arr_sched)) : []);
  const xev = $derived(xall.filter((e) => e.slack_obs != null));
  const xmade = $derived(xev.filter((e) => (e.slack_obs ?? 0) >= 180).length);
  const routeOf = (id: string | undefined) => s?.served.find((r) => r.route_id === id);
  const modesHere = $derived(s ? (["lrt", "streetcar", "rail", "bus"] as Mode[]).filter((m) => s.hours.some((h) => h[m])) : []);
  const hoursCovered = $derived(s ? s.hours.length : 0);
  // one row per route (the backend sums its scheduled arrivals over the bays it starts or ends at)
  const schedOnly = $derived(s?.sched_only ?? []);
  const served = $derived(s ? [...s.served].sort((a, b) => Number(a.mode === "bus") - Number(b.mode === "bus")) : []);
</script>

<ScopeBar crumbs={[["Stations", router.href("stations")], [name || "…", null]]} show={["dates", "days", "hours", "modes", "otp"]} />
{#if !s}
  <Loading error={res.error} />
{:else}
  <PageTitle title={name} sub="{s.station.n_stops} stops">
    {#snippet lead()}<span class="ring"><span></span></span>{/snippet}
    {#snippet right()}
      <span class="served">{#each served as r (r.route_id)}<a href={router.href(`routes/${r.route_id}/0`)}><RouteBullet short={r.short} color={r.color} mode={r.mode} size={22} /></a>{/each}</span>
      <Maturity days={app.days.length} hours={hoursCovered} />
    {/snippet}
  </PageTitle>
  <div class="page" class:dim={res.loading}>
    <div class="row wrap-md">
      <div class="col" style:width="560px" style:flex-shrink="0">
        <Panel q="What is at this station?" info="Stops merged into one station. Bays where every trip starts or ends have no realtime (UTA publishes none for first or last stops), so they show timetable figures only.">
          <div class="boxes">
            {#each boxes as b (b.key)}
              <div class="box" class:bay={b.terminal}>
                <div class="br">{#each b.routes as r}<RouteBullet short={r.short} color={r.color} mode={r.mode} size={18} />{/each}</div>
                <div class="bl">{b.label}{#if b.stops > 1}<span class="muted">&nbsp;· {b.stops} stops</span>{/if}</div>
                {#if b.terminal}<Tag kind="hatch">timetable only</Tag>
                {:else}<div class="bn"><b>{b.observed}</b><span>/ {b.sched}</span></div>{/if}
              </div>
            {/each}
          </div>
          <Legend items={[{ color: "var(--ink)", label: "observed / scheduled arrivals", kind: "sw" }]} />
        </Panel>

        <Panel q="When do vehicles arrive here?" info="Observed arrivals per hour on {dateLabel(s.scope.to)}, all stops of the station.">
          <StationArrivals hours={s.hours} gaps={s.gaps} colors={MODE_COLOR} />
          <Legend items={[...modesHere.map((m) => ({ color: MODE_COLOR[m], label: MODE_LABEL[m] })), { color: "", label: "no data", kind: "hatch" as const }]} />
        </Panel>

        {#if s.served.length >= 2}
          <Panel q="Would a connection have been made?" info="For each scheduled arrival of the first route, the next scheduled departure of the second 3–15 min later. Slack = departure minus arrival; a connection needs at least a 3 min walk. Grey ticks on the time axis: not observed. Shown for the last day of the range." cap={s.scope.from !== s.scope.to ? dateLabel(s.scope.to) : undefined} n={xev.length} warn={xev.length < 20}>
            {#snippet right()}
              <select aria-label="Transfer from" value={xfer?.from} onchange={(e) => router.set({ xf: (e.currentTarget as HTMLSelectElement).value, xt: xfer?.to })}>
                {#each served as r}<option value={r.route_id}>{r.short}</option>{/each}
              </select><span class="muted">→</span>
              <select aria-label="Transfer to" value={xfer?.to} onchange={(e) => router.set({ xt: (e.currentTarget as HTMLSelectElement).value, xf: xfer?.from })}>
                {#each served as r}<option value={r.route_id}>{r.short}</option>{/each}
              </select>
            {/snippet}
            {#if xfer && xall.length}
              <div class="xh">
                {#each [routeOf(xfer.from), routeOf(xfer.to)] as r, i}
                  {#if i}<span class="muted">→</span>{/if}{#if r}<RouteBullet short={r.short} color={r.color} mode={r.mode} size={20} />{/if}
                {/each}
                <span class="sp"></span>
                <Tag kind="ok">✓ {xmade}</Tag>{#if xev.length - xmade}<Tag kind="bad">✗ {xev.length - xmade}</Tag>{/if}
                {#if xall.length - xev.length}<Tag kind="hatch">{xall.length - xev.length} not observed</Tag>{/if}
              </div>
              <StationTransfer events={xall} color={routeOf(xfer.to) ? "var(--ok)" : "var(--ink)"} />
              <Legend items={[{ color: "var(--sched)", label: "timetable", kind: "line" }, { color: "var(--ok)", label: "made", kind: "dot" }, { color: "var(--late-3)", label: "missed", kind: "dot" }, { color: "var(--faint)", label: "not observed", kind: "line" }]} />
            {:else}
              <div class="none"><Tag>no scheduled connections</Tag></div>
            {/if}
          </Panel>
        {/if}
      </div>

      <div class="col grow">
        <Panel q="How is each route doing here?" info="Observed arrivals in the scope. Amber n: fewer than 10.">
          <table class="t">
            <thead><tr><th>Route · direction</th><th class="r">Arrivals</th><th class="r">On time</th><th class="r">Median delay</th><th class="r">Dwell</th></tr></thead>
            <tbody>
              {#each s.routes as r}
                <tr class="link" onclick={() => router.go(`routes/${r.route_id}/${r.direction_id}`)}>
                  <td><a class="rn" href={router.href(`routes/${r.route_id}/${r.direction_id}`)}><RouteBullet short={r.short} color={r.color} mode={r.mode} size={20} /><span>{r.head ?? ""}</span></a></td>
                  <td class="r"><NBadge n={r.n} warn={r.n < 10} /></td>
                  <td class="r">{pct(r.otp, 0)}</td>
                  <td class="r"><DelayCell s={r.median} /></td>
                  <td class="r">{dur(r.dwell)}</td>
                </tr>
              {/each}
              {#each schedOnly as r (r.route_id)}
                <tr class="link" onclick={() => router.go(`routes/${r.route_id}/0`)}>
                  <td><a class="rn" href={router.href(`routes/${r.route_id}/0`)}><RouteBullet short={r.short} color={r.color} mode={r.mode} size={20} /><span class="muted">{r.bays.length ? r.bays.join(", ") : "platform"}</span></a></td>
                  <td class="r muted">{r.sched} sched</td>
                  <td class="r muted">—</td>
                  <td class="r"><Tag kind="hatch">terminal · no realtime</Tag></td>
                  <td class="r muted">—</td>
                </tr>
              {/each}
              {#if !s.routes.length && !schedOnly.length}<tr><td colspan="5" class="muted">—</td></tr>{/if}
            </tbody>
          </table>
        </Panel>

        <Panel q={s.board.length ? `What happened ${clock(s.board[0].obs)}–${clock(lastObs)}?` : "What happened here?"} info="A departure board of the past: scheduled against what happened, on the last day of the range." cap={s.scope.from !== s.scope.to ? dateLabel(s.scope.to) : undefined}>
          {#if s.board.length}
            <table class="t">
              <thead><tr><th>Sched</th><th>Arrived</th><th class="r">Δ</th><th>Route</th><th>Trip</th><th class="r">Dwell</th></tr></thead>
              <tbody>
                {#each s.board as b (b.trip_id + b.obs)}
                  <tr>
                    <td class="mono">{clock(b.sched)}</td>
                    <td class="mono">{clock(b.obs, true)}</td>
                    <td class="r"><DelayCell s={b.delay} /></td>
                    <td><span class="rn"><RouteBullet short={b.short} color={b.color} mode={b.mode} size={20} /><span>{b.head ?? ""}</span></span></td>
                    <td><a class="mono" href={router.href(`trip/${b.trip_id}`, { date: s.scope.to }, false)}>{b.trip_id}</a></td>
                    <td class="r">{dur(b.dwell)}</td>
                  </tr>
                {/each}
              </tbody>
            </table>
          {:else}
            <div class="none"><Tag>no observed arrivals</Tag></div>
          {/if}
          <div class="nav">
            <button class="chip" onclick={earlier} disabled={!s.board.length}>◀ Earlier</button>
            <button class="chip" onclick={later} disabled={!router.get("until")}>Later ▶</button>
          </div>
        </Panel>
      </div>
    </div>
  </div>
{/if}

<style>
  .dim { opacity: .6; transition: opacity .15s; }
  .ring { width: 34px; height: 34px; border-radius: 50%; border: 3px solid var(--ink); display: grid; place-items: center; }
  .ring span { width: 12px; height: 12px; border-radius: 50%; background: var(--ink); }
  .served { display: flex; gap: 4px; flex-wrap: wrap; }
  .served a:hover { text-decoration: none; opacity: .8; }
  .boxes { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; }
  .box { border: 1px solid var(--border); border-radius: 4px; padding: 7px 9px; display: flex; flex-direction: column; gap: 5px; min-width: 0; }
  .box.bay { background: var(--panel-2); }
  .br { display: flex; gap: 3px; flex-wrap: wrap; }
  .bl { font-size: 11.5px; font-weight: 600; }
  .bn { font-size: 12px; color: var(--muted); display: flex; gap: 4px; align-items: baseline; }
  .bn b { font-size: 15px; color: var(--ink); font-weight: 650; }
  .rn { display: inline-flex; align-items: center; gap: 8px; color: var(--ink); max-width: 260px; }
  .rn span:last-child { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .xh { display: flex; gap: 6px; align-items: center; }
  .sp { flex: 1; }
  .nav { display: flex; gap: 8px; }
  .none { padding: 20px 0; }
  @media (max-width: 1100px) { .col[style] { width: auto !important; } }
  @media (max-width: 600px) { .boxes { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
</style>
