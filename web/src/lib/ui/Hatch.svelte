<script lang="ts">
  // <defs> for the "no data" hatch; use fill="url(#{id})".
  let { id }: { id: string } = $props();
</script>

<defs>
  <pattern {id} width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
    <rect width="6" height="6" fill="var(--panel)" /><line x1="0" y1="0" x2="0" y2="6" stroke="var(--hatch)" stroke-width="3" />
  </pattern>
</defs>
