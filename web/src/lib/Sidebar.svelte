<script lang="ts">
  import { store, MAX_COMPARISONS } from "./store.svelte";
  import ComparisonCard from "./ComparisonCard.svelte";
  import StopList from "./StopList.svelte";

  const full = $derived(store.comparisons.length >= MAX_COMPARISONS);
</script>

<section class="comparisons" aria-label="Comparisons">
  <div class="head">
    <div>
      <h2>Your rides</h2>
      <p class="muted small">Compare up to {MAX_COMPARISONS} stretches side by side</p>
    </div>
    <button class="btn" onclick={() => store.add()} disabled={full}
      title={full ? `Up to ${MAX_COMPARISONS} comparisons` : "Add a comparison"}>
      <span aria-hidden="true">+</span> Add
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
  .comparisons { padding: 18px 16px 16px; display: grid; grid-template-columns: minmax(0, 1fr); gap: 10px;
    border-bottom: 1px solid var(--border); background: var(--page); }
  .head { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 2px; }
</style>
