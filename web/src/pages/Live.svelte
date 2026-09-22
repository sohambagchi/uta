<script lang="ts">
  import ScopeBar from "../lib/ui/ScopeBar.svelte";
  import LiveMap from "../lib/LiveMap.svelte";
</script>

<ScopeBar crumbs={[["Live", null]]} show={[]} />
<div class="wrap"><LiveMap /></div>

<style>
  .wrap { position: relative; height: calc(100vh - var(--header-h) - 47px); min-height: 400px; }
</style>
