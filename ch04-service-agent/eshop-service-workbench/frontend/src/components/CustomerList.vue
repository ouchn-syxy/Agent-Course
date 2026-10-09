<script setup lang="ts">
import type { CustomerSummary } from '../types'

defineProps<{
  customers: CustomerSummary[]
  selectedId: string | null
}>()

const emit = defineEmits<{
  select: [id: string]
}>()

function typeLabel(c: CustomerSummary): string {
  if (c.need_human) return '⚠'
  if (c.is_handled) return '✓'
  if (c.unread_count > 1) return '●'
  return ''
}

function typeClass(c: CustomerSummary): string {
  if (c.need_human) return 'tag-urgent'
  if (c.is_handled) return 'tag-done'
  return 'tag-new'
}
</script>

<template>
  <div class="customer-list">
    <div class="list-header">
      <h3>消息列表</h3>
      <span class="total-badge">{{ customers.length }}</span>
    </div>
    <div class="list-body">
      <div
        v-for="c in customers"
        :key="c.id"
        class="customer-item"
        :class="{ active: c.id === selectedId, handled: c.is_handled }"
        @click="emit('select', c.id)"
      >
        <div class="customer-avatar">{{ c.avatar }}</div>
        <div class="customer-info">
          <div class="customer-top">
            <span class="customer-name">{{ c.name }}</span>
            <span class="customer-level">{{ c.level }}</span>
            <span v-if="typeLabel(c)" class="type-tag" :class="typeClass(c)">
              {{ typeLabel(c) }}
            </span>
          </div>
          <div class="customer-preview">{{ c.last_message }}</div>
          <div class="customer-time">{{ c.last_message_time }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.customer-list {
  width: 280px;
  min-width: 280px;
  background: #f8f9fb;
  border-right: 1px solid #e5e7eb;
  display: flex;
  flex-direction: column;
  height: 100%;
}

.list-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px;
  border-bottom: 1px solid #e5e7eb;
}

.list-header h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: #1f2937;
}

.total-badge {
  background: #e5e7eb;
  color: #6b7280;
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 10px;
}

.list-body {
  flex: 1;
  overflow-y: auto;
}

.customer-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 16px;
  cursor: pointer;
  border-bottom: 1px solid #f3f4f6;
  transition: background 0.15s;
}

.customer-item:hover {
  background: #eef2ff;
}

.customer-item.active {
  background: #e0e7ff;
}

.customer-item.handled {
  opacity: 0.65;
}

.customer-avatar {
  font-size: 28px;
  line-height: 1;
  flex-shrink: 0;
  margin-top: 2px;
}

.customer-info {
  flex: 1;
  min-width: 0;
}

.customer-top {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 3px;
}

.customer-name {
  font-size: 14px;
  font-weight: 600;
  color: #1f2937;
}

.customer-level {
  font-size: 10px;
  color: #9ca3af;
  background: #f3f4f6;
  padding: 1px 6px;
  border-radius: 3px;
}

.type-tag {
  font-size: 10px;
  font-weight: 600;
  margin-left: auto;
}

.tag-new { color: #3b82f6; }
.tag-urgent { color: #ef4444; }
.tag-done { color: #22c55e; }

.customer-preview {
  font-size: 12px;
  color: #6b7280;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.customer-time {
  font-size: 11px;
  color: #9ca3af;
  margin-top: 2px;
}
</style>
