<script setup>
/**
 * TimelineMessage —— 渲染两类消息气泡：
 *   - user:            右对齐，person 图标，primary-container 气泡
 *   - assistant_text:  左对齐，smart_toy 图标，surface 气泡（rounded-tl-none）
 *
 * 通过单个 item prop 传入，内部按 item.kind 分支；
 * 视觉与 WorkspaceView / AgentPane 现有气泡保持一致。
 */
defineProps({
  item: {
    type: Object,
    required: true,
    validator: (v) => v.kind === 'user' || v.kind === 'assistant_text',
  },
})
</script>

<template>
  <div
    class="flex gap-3"
    :class="{ 'flex-row-reverse': item.kind === 'user' }"
  >
    <!-- 头像 -->
    <div
      class="w-8 h-8 rounded-full flex items-center justify-center shrink-0"
      :style="{
        background:
          item.kind === 'user'
            ? 'var(--color-surface-container-high)'
            : 'var(--color-primary-container)',
        color:
          item.kind === 'user'
            ? 'var(--color-on-surface)'
            : 'var(--color-on-primary-container)',
      }"
    >
      <span class="material-symbols-outlined text-[20px]">{{
        item.kind === 'user' ? 'person' : 'smart_toy'
      }}</span>
    </div>

    <!-- 气泡 -->
    <div
      class="rounded-lg p-4 shadow-sm border whitespace-pre-wrap max-w-[85%]"
      :class="item.kind === 'user' ? 'rounded-tr-none' : 'rounded-tl-none'"
      :style="{
        background:
          item.kind === 'user'
            ? 'var(--color-primary-container)'
            : 'var(--color-surface)',
        borderColor: 'var(--color-outline-variant)',
        color:
          item.kind === 'user'
            ? 'var(--color-on-primary-container)'
            : 'var(--color-on-surface)',
      }"
    >
      <p class="text-[15px]">{{ item.text }}</p>
    </div>
  </div>
</template>
