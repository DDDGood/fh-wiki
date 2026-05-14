<script setup lang="ts">
import { useData } from 'vitepress'
const { frontmatter } = useData()

const LABELS: Record<string, { text: string; color: string }> = {
  general: { text: '🌐 通用原理', color: '#10b981' },
  horizon: { text: '🏁 Horizon 系列', color: '#3b82f6' },
  fh4: { text: 'FH4', color: '#6b7280' },
  fh5: { text: 'FH5', color: '#f59e0b' },
  fh6: { text: 'FH6', color: '#8b5cf6' },
}
</script>

<template>
  <div v-if="Array.isArray(frontmatter.applies_to) && frontmatter.applies_to.length" class="applies-to">
    <span
      v-for="key in frontmatter.applies_to"
      :key="key"
      class="badge"
      :style="{ backgroundColor: LABELS[key]?.color || '#999' }"
      :title="key"
    >{{ LABELS[key]?.text || key }}</span>
  </div>
</template>

<style scoped>
.applies-to {
  display: flex;
  gap: 6px;
  margin: -8px 0 16px;
  flex-wrap: wrap;
}
.badge {
  display: inline-block;
  padding: 2px 10px;
  border-radius: 12px;
  font-size: 12px;
  font-weight: 500;
  color: white;
  line-height: 1.6;
}
</style>
