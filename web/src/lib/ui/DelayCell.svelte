<script lang="ts">
  import { dcol, delay } from "../format";
  let { s }: { s: number | null | undefined } = $props();
</script>

<span class="dc"><span class="sw" style:background={dcol(s)}></span>{delay(s)}</span>

<style>
  .dc { display: inline-flex; align-items: center; gap: 6px; justify-content: flex-end; font-variant-numeric: tabular-nums; }
  .sw { width: 8px; height: 8px; border-radius: 2px; flex: none; }
</style>
