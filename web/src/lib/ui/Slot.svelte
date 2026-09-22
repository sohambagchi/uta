<script lang="ts">
  let { i, size = 22 }: { i: number; size?: number } = $props();
</script>

<span class="bullet" style:--b="{size}px" style:--c="var(--slot-{i + 1})">{"ABCD"[i]}</span>
