<script lang="ts">
  // Skeleton in the final layout; no spinners.
  let { error = null, rows = 3 }: { error?: string | null; rows?: number } = $props();
</script>

{#if error}
  <div class="err">{error}</div>
{:else}
  <div class="sk">
    <div class="b" style:width="40%" style:height="18px"></div>
    <div class="kp">{#each Array(5) as _}<div class="b" style:height="70px"></div>{/each}</div>
    {#each Array(rows) as _}<div class="b" style:height="220px"></div>{/each}
  </div>
{/if}

<style>
  .sk { display: flex; flex-direction: column; gap: 14px; padding: 18px 20px; }
  .kp { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; }
  .b { background: var(--sunk); border-radius: 4px; }
  .err { margin: 20px; padding: 10px 14px; border-radius: 4px; background: var(--bad-bg); color: var(--bad-ink); font-size: 12.5px; }
</style>
