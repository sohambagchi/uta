<script lang="ts">
  import type { Series } from "../series";
  import { store } from "../store.svelte";
  import { vsSchedule } from "../stats";
  import { dur, pct } from "../format";
  import Panel from "../ui/Panel.svelte";
  import Slot from "../ui/Slot.svelte";
  import RouteBullet from "../ui/RouteBullet.svelte";
  import NBadge from "../ui/NBadge.svelte";
  import DelayCell from "../ui/DelayCell.svelte";
  import Tag from "../ui/Tag.svelte";

  let { series }: { series: Series[] } = $props();
  const rows = $derived(series.map((s) => ({ s, delta: vsSchedule(s.trips), r: store.routeById.get(s.seg.route_id) })));
  const mode = (t: number | undefined) => (t === 3 ? "bus" : t === 2 ? "rail" : "lrt");
  const st = (n: string) => n.replace(/ Station$/, "");
</script>

<Panel q="How long does each stretch take?"
  info="Departure at the first stop to arrival at the second. Buffer = (p95 − median) / median: the extra time to allow to arrive on time 19 times in 20. CV = std dev / mean. Timetable figures are weighted by how many days each trip runs; trips/wk counts timetabled trips in a typical week matching the filters.">
  <table class="t">
    <thead><tr>
      <th>Slot</th><th class="r">Trips</th><th class="r">Median</th><th class="r">Mean</th><th class="r">p10–p90</th><th class="r">p95</th>
      <th class="r">Std dev</th><th class="r">CV</th><th class="r">Buffer</th><th class="r">Timetable</th><th class="r">Trips/wk</th><th class="r">vs timetable</th>
    </tr></thead>
    <tbody>
      {#each rows as { s, delta, r } (s.c.id)}
        {@const o = s.obs}
        <tr class="link" class:on={s.c.id === store.activeId} onclick={() => (store.activeId = s.c.id)}>
          <td><span class="who"><Slot i={s.c.slot} size={20} />
            {#if r}<RouteBullet short={r.route_short_name} color={r.route_color} mode={mode(r.route_type)} size={20} />{/if}
            <span class="seg">{st(s.seg.from.name)} → {st(s.seg.to.name)}</span></span></td>
          <td class="r"><NBadge n={s.trips.length} warn={s.trips.length < 20} /></td>
          {#if o}
            <td class="r"><b>{dur(o.median)}</b></td><td class="r">{dur(o.mean)}</td><td class="r">{dur(o.p10)}–{dur(o.p90)}</td>
            <td class="r">{dur(o.p95)}</td><td class="r">{dur(o.std)}</td><td class="r">{pct(o.cv, 0)}</td><td class="r">{pct(o.buffer, 0)}</td>
          {:else}
            <td class="r" colspan="7"><Tag kind="hatch">no observed trips</Tag></td>
          {/if}
          <td class="r">{dur(s.schedMedian)}</td><td class="r mono">{s.schedTrips.toLocaleString()}</td>
          <td class="r"><DelayCell s={delta} /></td>
        </tr>
      {/each}
    </tbody>
  </table>
</Panel>

<style>
  .who { display: inline-flex; align-items: center; gap: 7px; }
  .seg { max-width: 300px; overflow: hidden; text-overflow: ellipsis; color: var(--ink-2); }
  tr.on td { background: var(--panel-2); }
  b { font-weight: 650; font-size: 13.5px; }
</style>
