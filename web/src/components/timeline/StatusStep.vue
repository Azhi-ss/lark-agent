<script setup>
/**
 * StatusStep —— timeline 中的状态步骤行。
 * active: 旋转 sync 图标（primary），表示进行中
 * done:   check_circle 图标（success），表示已完成
 */
defineProps({
  label: { type: String, required: true },
  state: {
    type: String,
    default: 'active',
    validator: (v) => v === 'active' || v === 'done',
  },
})
</script>

<template>
  <div
    class="flex items-center gap-2 text-[13px]"
    :style="{ color: 'var(--color-on-surface-variant)' }"
  >
    <span
      class="material-symbols-outlined text-[16px]"
      :class="{ spin: state === 'active' }"
      :style="{
        color:
          state === 'active'
            ? 'var(--color-primary)'
            : 'var(--color-success-text)',
      }"
    >
      {{ state === 'active' ? 'sync' : 'check_circle' }}
    </span>
    <span
      :style="{
        color:
          state === 'active'
            ? 'var(--color-on-surface)'
            : 'var(--color-on-surface-variant)',
      }"
      >{{ label }}</span
    >
  </div>
</template>
