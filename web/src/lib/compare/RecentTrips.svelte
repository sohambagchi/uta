<script lang="ts">
  import type { Series } from "../series";
  import { TZ, dur, DOW } from "../format";
  import { router } from "../router.svelte";
  import Panel from "../ui/Panel.svelte";
  import DelayCell from "../ui/DelayCell.svelte";
  import Tag from "../ui/Tag.svelte";

  let { s }: { s: Series } = $props();
  const LIMIT = 200;
  const clock = new Intl.DateTimeFormat("en-GB", { timeZone: TZ, hour: "2-digit", minute: "2-digit" });
  const rows = $derived([...s.trips].reverse().slice(0, LIMIT));
</script>

<Panel q="Which trips were these?" info="Latest {LIMIT} observed trips of the selected slot that match the filters. Left late = departure delay at the first stop."
  n={s.trips.length} nLabel="trips">
  {#snippet right()}<span class="who"><span class="bullet sm" style:--c={s.color}>{s.letter}</span>{s.routeShort}</span>{/snippet}
  <div class="scroll">
    <table class="t">
      <thead><tr><th>Date</th><th>Left</th><th>Trip</th><th>Vehicle</th><th class="r">Took</th><th class="r">Timetable</th>
        <th class="r">vs timetable</th><th class="r">Left late</th></tr></thead>
      <tbody>
        {#each rows as t (t.date + t.tripId)}
          <tr>
            <td class="mono">{DOW[t.dow]} {t.date}</td>
            <td class="mono">{clock.format(t.depart * 1000)}</td>
            <td><a class="mono" href={router.href(`trip/${t.tripId}`, { date: t.date }, false)}>{t.tripId}</a></td>
            <td>{#if t.vehicleId}<a class="mono" href={router.href(`vehicle/${t.vehicleId}`, { date: t.date }, false)}>{t.vehicleId}</a>{:else}—{/if}</td>
            <td class="r"><b>{dur(t.dur)}</b></td>
            <td class="r">{dur(t.sched)}</td>
            <td class="r"><DelayCell s={t.sched != null ? t.dur - t.sched : null} /></td>
            <td class="r"><DelayCell s={t.depDelay} /></td>
          </tr>
        {:else}
          <tr><td colspan="8"><Tag kind="hatch">no observed trips match the filters</Tag></td></tr>
        {/each}
      </tbody>
    </table>
  </div>
</Panel>

<style>
  .scroll { max-height: 420px; overflow: auto; }
  thead th { position: sticky; top: 0; background: var(--panel); z-index: 1; }
  .who { display: inline-flex; align-items: center; gap: 6px; font-weight: 650; font-size: 12.5px; }
  b { font-weight: 650; }
</style>
