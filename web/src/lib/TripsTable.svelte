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
    <h2><span class="key" style:background={s.color}></span> {s.letter}: trips</h2>
    <p>{s.label}. Latest {Math.min(LIMIT, s.trips.length)} of {s.trips.length.toLocaleString()} observed trips matching the filters.</p>
  </figcaption>
  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>Date</th><th>Departed</th><th>Vehicle</th>
          <th class="num">Minutes</th><th class="num">Scheduled</th><th class="num">vs sched.</th>
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
            <td class="num" class:up={diff != null && diff > 30} class:down={diff != null && diff < -30}>{fmtSignedMin(diff)}</td>
            <td class="num">{fmtSignedMin(t.depDelay)}</td>
          </tr>
        {:else}
          <tr><td colspan="7" class="muted">No observed trips match the filters yet.</td></tr>
        {/each}
      </tbody>
    </table>
  </div>
</figure>

<style>
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 14px 16px; margin: 0; }
  figcaption { margin-bottom: 10px; }
  figcaption h2 { display: flex; align-items: center; gap: 8px; }
  figcaption p { color: var(--muted); font-size: 12px; margin-top: 2px; }
  .table-wrap { overflow: auto; max-height: 420px; }
  table { border-collapse: collapse; width: 100%; font-size: 13px; }
  th, td { padding: 5px 8px; border-bottom: 1px solid var(--grid); white-space: nowrap; text-align: left; }
  th { color: var(--ink-2); font-weight: 500; font-size: 12px; position: sticky; top: 0; background: var(--surface); }
  tbody tr:hover td { background: var(--surface-2); }
  .up { color: var(--delta-up); }
  .down { color: var(--delta-down); }
</style>
