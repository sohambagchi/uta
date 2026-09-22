<script lang="ts">
  import { insights } from "../lib/api";
  import { app, load } from "../lib/app.svelte";
  import { router } from "../lib/router.svelte";
  import { clock, dateLabel } from "../lib/format";
  import ScopeBar from "../lib/ui/ScopeBar.svelte";
  import PageTitle from "../lib/ui/PageTitle.svelte";
  import Panel from "../lib/ui/Panel.svelte";
  import Tag from "../lib/ui/Tag.svelte";
  import NBadge from "../lib/ui/NBadge.svelte";
  import Legend from "../lib/ui/Legend.svelte";
  import RouteBullet from "../lib/ui/RouteBullet.svelte";
  import DelayCell from "../lib/ui/DelayCell.svelte";
  import Loading from "../lib/ui/Loading.svelte";
  import VehicleGantt from "../lib/charts/VehicleGantt.svelte";
  import TripGps from "../lib/charts/TripGps.svelte";

  let { vehicleId }: { vehicleId: string } = $props();
  // the day's GPS loads on demand (gps=1 keeps it open in the URL)
  const showGps = $derived(router.get("gps") === "1");
  const gps = load(() => (showGps ? insights.vehicleGps(vehicleId, router.get("date") ?? undefined) : null));
  $effect(() => { if (showGps) app.loadNetwork(); });
  const res = load(() => { app.tick; return insights.vehicle(vehicleId, router.get("date") ?? undefined); });
  const v = $derived(res.data);
  const routes = $derived(v ? [...new Map(v.trips.map((t) => [t.route_id, t])).values()] : []);
  const pairs = $derived(v ? v.trips.slice(1).map((b, k) => {
    const a = v.trips[k];
    const lay = a.sched_end != null && b.sched_start != null ? b.sched_start - a.sched_end : null;
    let outcome: "carried" | "absorbed" | "ontime" | "none" = "none";
    if (a.d_last != null && b.d_first != null) outcome = a.d_last <= 60 ? "ontime" : b.d_first > 60 ? "carried" : "absorbed";
    return { a, b, lay, outcome };
  }) : []);
  const swaps = $derived(v ? v.trips.filter((t) => t.swapped_with.length).length : 0);
  const first = $derived(v?.trips.find((t) => t.obs_start != null));
  const last = $derived(v ? [...v.trips].reverse().find((t) => t.obs_end != null) : undefined);
  const kind = $derived(v?.trips.length && v.trips.every((t) => t.mode === "bus") ? "Bus"
    : v?.trips.some((t) => t.mode === "rail") ? "Train" : v?.trips.some((t) => t.mode === "lrt" || t.mode === "streetcar") ? "Railcar" : "Vehicle");
</script>

<ScopeBar crumbs={[["Trips & vehicles", router.href("trips")], ["Vehicle " + vehicleId, null]]} show={[]}>
  {#snippet extra()}
    {#if v}
      <label class="dt"><span class="lab">Date</span>
        <select aria-label="Service date" value={v.date} disabled={v.days.length < 2}
          onchange={(e) => router.set({ date: (e.currentTarget as HTMLSelectElement).value })}>
          {#each v.days.includes(v.date) ? v.days : [...v.days, v.date] as d}<option value={d}>{dateLabel(d)}</option>{/each}
        </select>
      </label>
    {/if}
  {/snippet}
</ScopeBar>
{#if !v}
  <Loading error={res.error} />
{:else}
  <PageTitle title="{kind} {v.vehicle_id}" sub="{dateLabel(v.date)}{first ? ` · ${clock(first.obs_start)}–${clock(last?.obs_end)}` : ''}">
    {#snippet lead()}<span class="vid">{v.vehicle_id}</span>{/snippet}
    {#if v.blocks.length}<span class="hs">block {v.blocks.join(", ")}</span>{/if}
    {#snippet right()}
      <Tag>{v.trips.length} trips</Tag>
      <span class="rts">{#each routes as r}<RouteBullet short={r.short} color={r.color} mode={r.mode} size={20} />{/each}</span>
      {#if routes.length > 1}<Tag>{routes.length} routes interlined</Tag>{/if}
      <Tag kind={swaps ? "warn" : "info"}>{swaps} swaps</Tag>
      <button class="chip" aria-pressed={showGps} onclick={() => router.set({ gps: showGps ? null : 1 })}>{showGps ? "Hide" : "Show"} GPS for the day</button>
    {/snippet}
  </PageTitle>
  <div class="page" class:dim={res.loading}>
    {#if !v.trips.length}
      <div><Tag kind="warn">no trips on {dateLabel(v.date)}</Tag></div>
    {:else}
      <Panel q="What did this vehicle do all day?" info="Scheduled trips (dashed) above what was observed: bars run from the first to the last observed stop, end dots show the delay there. Click a bar to open the trip." n={v.trips.length} nLabel="trips" warn={false}>
        <VehicleGantt trips={v.trips} gaps={v.gaps} date={v.date} />
        <Legend delay items={[{ color: "var(--sched)", label: "scheduled", kind: "dash" }, { color: "var(--ink)", label: "observed" }, { color: "", label: "no data", kind: "hatch" }]} />
      </Panel>
      {#if showGps}
        <Panel q="Where did it go all day?" info="GPS pings over the service day; trips alternate between two tones, faint between trips. Hover for the time and trip."
          n={gps.data?.pings.length ?? "…"} nLabel="pings" warn={false} loading={gps.loading}>
          {#if gps.error}<Tag kind="bad">{gps.error}</Tag>
          {:else if gps.data && gps.data.pings.length > 1}
            <TripGps gps={gps.data.pings} context={app.lines} colorBy="trip" height={420} />
            <Legend items={[{ color: "var(--ink)", label: "trips 1, 3, …", kind: "line" }, { color: "var(--sched)", label: "trips 2, 4, …", kind: "line" }, { color: "var(--faint)", label: "between trips", kind: "line" }]} />
          {:else if gps.data}<Tag kind="hatch">no GPS</Tag>
          {:else}<div class="sk"></div>{/if}
        </Panel>
      {/if}
      <div class="row wrap-md">
        <Panel q="Does lateness carry into the next trip?" info="Delay at the last observed stop vs the first observed stop of the next trip. Absorbed: a late arrival left on time after the layover." w={620}>
          <table class="t">
            <thead><tr><th>Trip → next</th><th class="r">Arrived</th><th class="r">Layover</th><th class="r">Next departed</th><th>Outcome</th></tr></thead>
            <tbody>
              {#each pairs as p}
                <tr>
                  <td><span class="pair"><RouteBullet short={p.a.short} color={p.a.color} mode={p.a.mode} size={18} />→<RouteBullet short={p.b.short} color={p.b.color} mode={p.b.mode} size={18} /></span></td>
                  <td class="r"><DelayCell s={p.a.d_last} /></td>
                  <td class="r">{p.lay != null ? `${Math.round(p.lay / 60)} min` : "—"}</td>
                  <td class="r"><DelayCell s={p.b.d_first} /></td>
                  <td>
                    {#if p.outcome === "carried"}<b class="bad">carried over</b>
                    {:else if p.outcome === "absorbed"}<b class="ok">absorbed</b>
                    {:else}<span class="muted">—</span>{/if}
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        </Panel>
        <Panel q="Trips in sequence" info="Click a row to open the trip." grow>
          <table class="t">
            <thead><tr><th>Route · to</th><th>Trip</th><th>Scheduled</th><th class="r">Stops seen</th><th class="r">Start</th><th class="r">End</th></tr></thead>
            <tbody>
              {#each v.trips as t (t.trip_id)}
                <tr class="link" onclick={() => router.go(`trip/${t.trip_id}`, { date: v.date })}>
                  <td><span class="pair"><RouteBullet short={t.short} color={t.color} mode={t.mode} size={20} /><span class="hd">{(t.head ?? "").replace(/ Station$/, "")}</span></span></td>
                  <td><a class="mono" href={router.href(`trip/${t.trip_id}`, { date: v.date })}>{t.trip_id}</a></td>
                  <td class="mono">{clock(t.sched_start)}–{clock(t.sched_end)}</td>
                  <td class="r">{#if t.in_gap}<Tag kind="hatch">{t.n} · outage</Tag>{:else}<NBadge n={t.n} label="" warn={t.n < 5} />{/if}</td>
                  <td class="r"><DelayCell s={t.d_first} /></td>
                  <td class="r"><DelayCell s={t.d_last} /></td>
                </tr>
              {/each}
            </tbody>
          </table>
        </Panel>
      </div>
    {/if}
  </div>
{/if}

<style>
  .dim { opacity: .6; transition: opacity .15s; }
  .dt { display: flex; align-items: center; gap: 4px; }
  .lab { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: .06em; font-weight: 600; font-stretch: 90%; margin-right: 3px; }
  .sk { height: 420px; background: var(--sunk); border-radius: 4px; }
  .vid { display: inline-flex; align-items: center; height: 34px; padding: 0 10px; border-radius: 4px; border: 2px solid var(--ink);
    font-family: var(--mono); font-weight: 600; font-size: 16px; }
  .hs { font-size: 20px; color: var(--muted); font-weight: 450; margin-left: 8px; }
  .rts { display: inline-flex; gap: 4px; }
  .pair { display: inline-flex; gap: 6px; align-items: center; }
  .hd { max-width: 220px; overflow: hidden; text-overflow: ellipsis; }
  .ok { color: var(--ok); font-weight: 600; }
  .bad { color: var(--late-3); font-weight: 600; }
</style>
