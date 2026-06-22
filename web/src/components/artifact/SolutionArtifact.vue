<script setup>
import { computed } from 'vue'

/**
 * solution artifact 详情：title + summary 徽标 + markdown 预览 + 导出/覆盖按钮。
 * - 导出 .md 始终启用
 * - 覆盖当前方案仅 isLatest 启用（旧版本只读）
 * - markdown 区 flex-1 滚动，按钮固定底部
 */
const props = defineProps({
  payload: { type: Object, default: () => ({}) }, // { title, markdown, summary }
  isLatest: { type: Boolean, default: false },
})
defineEmits(['exportSolution', 'overwriteSolution'])

const title = computed(() => props.payload?.title || '生成的方案')
const summary = computed(() => props.payload?.summary || '')
const markdown = computed(() => props.payload?.markdown || '')
</script>

<template>
  <div class="flex-1 flex flex-col min-h-0 p-4 gap-3">
    <!-- 标题 + summary 徽标 + 最新徽标 -->
    <div class="flex items-center gap-2 flex-wrap shrink-0">
      <h3
        class="text-[16px] font-semibold"
        :style="{ color: 'var(--color-on-surface)' }"
      >{{ title }}</h3>
      <span
        v-if="summary"
        class="px-2 py-0.5 rounded-sm text-[11px]"
        :style="{
          background: 'rgba(99, 14, 212, 0.1)',
          color: 'var(--color-primary)',
        }"
      >{{ summary }}</span>
      <span
        v-if="isLatest"
        class="px-1.5 py-0.5 rounded-sm text-[10px] font-medium"
        :style="{
          background: 'rgba(99, 14, 212, 0.1)',
          color: 'var(--color-primary)',
        }"
      >最新</span>
    </div>

    <!-- markdown 预览（whitespace-pre-wrap + mono + 滚动） -->
    <div
      class="flex-1 min-h-0 overflow-y-auto rounded-lg border p-4 whitespace-pre-wrap text-[13px]"
      style="font-family: 'JetBrains Mono', ui-monospace, monospace"
      :style="{
        background: 'var(--color-surface-container-lowest)',
        borderColor: 'var(--color-outline-variant)',
        color: 'var(--color-on-surface)',
      }"
    >{{ markdown }}</div>

    <!-- 操作按钮（固定底部） -->
    <div class="flex items-center gap-2 flex-wrap shrink-0">
      <button
        type="button"
        @click="$emit('exportSolution')"
        class="flex-1 min-w-[140px] px-4 py-2.5 rounded-lg text-[14px] font-medium transition-colors flex items-center justify-center gap-2"
        :style="{
          background: 'var(--color-secondary)',
          color: 'var(--color-on-secondary)',
        }"
      >
        <span class="material-symbols-outlined text-[18px]">download</span>
        导出 .md
      </button>
      <button
        type="button"
        @click="$emit('overwriteSolution')"
        :disabled="!isLatest"
        :title="!isLatest ? '旧版本只读' : ''"
        class="flex-1 min-w-[140px] px-4 py-2.5 rounded-lg text-[14px] font-medium transition-colors flex items-center justify-center gap-2 border disabled:opacity-50 disabled:cursor-not-allowed"
        :style="{
          background: 'var(--color-surface-container-lowest)',
          borderColor: 'var(--color-outline-variant)',
          color: 'var(--color-on-surface)',
        }"
      >
        <span class="material-symbols-outlined text-[18px]">sync</span>
        {{ isLatest ? '覆盖当前方案' : '覆盖已禁用（旧版本）' }}
      </button>
    </div>
  </div>
</template>
