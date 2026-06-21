<script setup>
defineProps({
  pendingCount: { type: Number, default: 0 },
  applyStatus: { type: String, default: '' },
  applying: { type: Boolean, default: false },
})
defineEmits(['apply'])
</script>

<template>
  <footer
    class="h-20 shrink-0 flex items-center justify-between px-6 z-40"
    :style="{
      background: 'var(--color-surface-container)',
      borderTop: '1px solid var(--color-outline-variant)',
    }"
  >
    <!-- 左：安全提示 / 状态 -->
    <div class="flex items-center gap-2 min-w-0">
      <span
        class="material-symbols-outlined text-[20px]"
        :style="{ color: 'var(--color-secondary)' }"
        >warning</span
      >
      <span
        class="text-[11px] uppercase font-bold tracking-wider truncate"
        style="font-family: 'Inter', sans-serif"
        :style="{ color: 'var(--color-secondary)' }"
      >
        安全提示：AI 生成内容在写回前请务必审阅。
      </span>
      <span
        v-if="applyStatus"
        class="ml-4 text-sm truncate"
        :style="{ color: 'var(--color-on-surface-variant)' }"
      >
        {{ applyStatus }}
      </span>
    </div>

    <!-- 右：协议链接 + 写回按钮 -->
    <div class="flex items-center gap-4">
      <div class="flex gap-4 mr-4">
        <a
          href="#"
          class="text-[11px] uppercase font-bold tracking-wider transition-colors"
          :style="{ color: 'var(--color-on-surface-variant)' }"
          >服务协议</a
        >
        <a
          href="#"
          class="text-[11px] uppercase font-bold tracking-wider transition-colors"
          :style="{ color: 'var(--color-on-surface-variant)' }"
          >隐私政策</a
        >
      </div>
      <button
        @click="$emit('apply')"
        :disabled="pendingCount === 0 || applying"
        class="px-6 py-2.5 rounded-lg text-sm font-medium shadow-sm transition-colors flex items-center gap-2 disabled:opacity-40 disabled:cursor-not-allowed"
        :style="{
          background: 'var(--color-secondary)',
          color: 'var(--color-on-secondary)',
        }"
      >
        <span class="material-symbols-outlined">sync</span>
        确认并写回飞书<span v-if="pendingCount > 0">（{{ pendingCount }} 块）</span>
      </button>
    </div>
  </footer>
</template>
