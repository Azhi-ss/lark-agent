<script setup>
import { ref, watch } from 'vue'

/**
 * ThinkingSummary —— 思考过程折叠卡。
 * 默认折叠（<details>），summary 显示「思考过程」。
 * running=true 时 summary 展示旋转 sync 图标 + 「正在思考...」；
 * running=false 时展示 check/expand 图标 + 「思考过程（已完成）」。
 *
 * 流式增量到达时自动展开一次，让用户看到正在思考；完成后保持当前开合状态。
 * 视觉与 AgentPane thinking card / WorkspaceView details 一致：
 * thinking-gray 背景 + outline-variant 边框 + JetBrains Mono 字体。
 */
const props = defineProps({
  text: { type: String, default: '' },
  running: { type: Boolean, default: false },
})

const open = ref(false)

// 首次有内容时自动展开，方便观察流式思考
watch(
  () => props.text,
  (t) => {
    if (t && !open.value && props.running) open.value = true
  },
)
</script>

<template>
  <details
    v-if="text || running"
    :open="open"
    @toggle="open = $event.target.open"
    class="rounded-lg border text-[13px]"
    :style="{
      background: 'var(--color-thinking-gray)',
      borderColor: 'var(--color-outline-variant)',
      color: 'var(--color-on-surface-variant)',
    }"
  >
    <summary
      class="cursor-pointer px-3 py-2 flex items-center gap-2 list-none"
      style="font-family: 'JetBrains Mono', ui-monospace, monospace"
    >
      <span
        class="material-symbols-outlined text-[16px]"
        :class="{ spin: running }"
        :style="{ color: 'var(--color-primary)' }"
        >{{ running ? 'sync' : 'psychology' }}</span
      >
      <span>{{ running ? '正在思考...' : '思考过程（已完成）' }}</span>
      <span
        class="material-symbols-outlined text-[16px] ml-auto"
        :style="{ color: 'var(--color-outline)' }"
        >{{ open ? 'expand_less' : 'expand_more' }}</span
      >
    </summary>
    <div
      v-if="text"
      class="px-3 py-2 whitespace-pre-wrap border-t"
      :style="{
        background: 'var(--color-surface-container-lowest)',
        borderColor: 'var(--color-outline-variant)',
      }"
      style="font-family: 'JetBrains Mono', ui-monospace, monospace"
    >{{ text }}</div>
  </details>
</template>
