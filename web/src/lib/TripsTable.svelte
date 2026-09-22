<script lang="ts">
  import type { Series } from "./series";
  import { DOW, TZ, fmtMin, fmtSignedMin } from "./format";

  let { s }: { s: Series } = $props();
  const LIMIT = 200;

  const fmtTime = new Intl.DateTimeFormat(undefined, { timeZone: TZ, hour: "numeric", minute: "2-digit" });
  const rows = $derived([...s.trips].reverse().slice(0, LIMIT));
</script>

<figure class="card">
  <figcaption>
    <h2><span class="bullet" style:--c={s.color}>{s.letter}</span> Recent rides</h2>
    <p>{s.label}. Latest {Math.min(LIMIT, s.trips.length)} of {s.trips.length.toLocaleString()} measured rides matching the filters.</p>
  </figcaption>
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>Date</th><th>Left at</th><th>Vehicle</th>
          <th class="num">Minutes</th><th class="num">Timetable</th><th class="num">vs timetable</th>
          <th class="num" title="How late the vehicle left the first stop">Left late by</th>
        </tr>
      </thead>
      <tbody>
        {#each rows as t (t.date + t.tripId)}
          {@const diff = t.sched != null ? t.dur - t.sched : null}
          <tr>
            <td>{DOW[t.dow]} {t.date}</td>
            <td>{fmtTime.format(t.depart * 1000)}</td>
            <td>{t.vehicleId ?? "–"}</td>
            <td class="num">{fmtMin(t.dur)}</td>
            <td class="num">{fmtMin(t.sched)}</td>
            <td class="num"><span class="delta" class:up={diff != null && diff > 30} class:down={diff != null && diff < -30}>{fmtSignedMin(diff)}</span></td>
            <td class="num">{fmtSignedMin(t.depDelay)}</td>
          </tr>
        {:else}
          <tr><td colspan="7" class="muted">No measured rides match the filters yet.</td></tr>
        {/each}
      </tbody>
    </table>
  </div>
</figure>

<style>
  figcaption h2 { display: flex; align-items: center; gap: 8px; }
  .table-wrap { overflow: auto; max-height: 440px; margin: 0 -8px; }
  table { border-collapse: collapse; width: 100%; font-size: 14px; }
  th, td { padding: 7px 10px; border-bottom: 1px solid var(--grid); white-space: nowrap; text-align: left; }
  th { color: var(--muted); font-weight: 600; font-size: 12px; position: sticky; top: 0; background: var(--surface); }
  tbody tr:hover td { background: var(--surface-2); }
  .delta { display: inline-block; padding: 0 7px; border-radius: 999px; font-weight: 600; }
  .up { color: var(--delta-up); background: color-mix(in srgb, var(--delta-up) 11%, transparent); }
  .down { color: var(--delta-down); background: color-mix(in srgb, var(--delta-down) 11%, transparent); }
</style>
