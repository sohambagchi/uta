<script lang="ts">
  import { store, MAX_COMPARISONS } from "./store.svelte";
  import ComparisonCard from "./ComparisonCard.svelte";
  import StopList from "./StopList.svelte";
</script>

<section class="comparisons" aria-label="Comparisons">
  <div class="head">
    <h2>Compare segments</h2>
    <button class="add" onclick={() => store.add()} disabled={store.comparisons.length >= MAX_COMPARISONS}
      title={store.comparisons.length >= MAX_COMPARISONS ? `Up to ${MAX_COMPARISONS} comparisons` : "Add a comparison"}>
      + Add
    </button>
  </div>
  {#each store.comparisons as c (c.id)}
    <ComparisonCard {c} />
  {/each}
</section>

{#if store.active}
  <StopList c={store.active} />
{/if}

<style>
  .comparisons { padding: 14px 14px 12px; display: grid; grid-template-columns: minmax(0, 1fr); gap: 8px; border-bottom: 1px solid var(--border); }
  .head { display: flex; align-items: center; justify-content: space-between; }
  .add { border: 1px solid var(--border); background: var(--surface); border-radius: 8px; padding: 3px 10px;
    font-size: 12px; color: var(--ink-2); }
  .add:hover:not(:disabled) { background: var(--surface-2); color: var(--ink); }
  .add:disabled { opacity: .5; cursor: default; }
</style>
