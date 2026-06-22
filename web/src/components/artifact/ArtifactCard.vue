<script setup>
import { computed } from 'vue'

/**
 * 内联摘要卡：artifact 的折叠形态，点击整卡 emit('open') 打开 Drawer 完整审阅。
 * 复用现有建议卡/方案卡视觉：紫色图标 + 紫色边框 + 轻投影 + 最新徽标。
 */
const props = defineProps({
  artifact: { type: Object, required: true }, // AgentArtifact
  isLatest: { type: Boolean, default: false },
})
defineEmits(['open'])

const icon = computed(() =>
  props.artifact?.artifact_type === 'solution' ? 'article' : 'edit_note',
)
const defaultTitle = computed(() =>
  props.artifact?.artifact_type === 'solution' ? '生成的方案' : '文档修改建议',
)
</script>

<template>
  <button
    type="button"
    @click="$emit('open')"
    class="w-full text-left rounded-lg border p-3 transition-colors hover:bg-[var(--color-surface-container)] fade-in"
    :style="{
      background: 'var(--color-surface)',
      borderColor: 'rgba(99, 14, 212, 0.3)',
      boxShadow: '0 4px 12px rgba(99, 14, 212, 0.06)',
    }"
  >
    <div class="flex items-start gap-3">
      <span
        class="material-symbols-outlined text-[22px] shrink-0 mt-0.5"
        :style="{ color: 'var(--color-primary)' }"
      >{{ icon }}</span>
      <div class="flex-1 min-w-0">
        <div class="flex items-center gap-2">
          <span
            class="text-[14px] font-semibold truncate"
            :style="{ color: 'var(--color-on-surface)' }"
          >{{ artifact.title || defaultTitle }}</span>
          <span
            v-if="isLatest"
            class="shrink-0 px-1.5 py-0.5 rounded-sm text-[10px] font-medium"
            :style="{
              background: 'rgba(99, 14, 212, 0.1)',
              color: 'var(--color-primary)',
            }"
          >最新</span>
        </div>
        <p
          v-if="artifact.summary"
          class="text-[12px] mt-0.5 line-clamp-2"
          :style="{ color: 'var(--color-on-surface-variant)' }"
        >{{ artifact.summary }}</p>
      </div>
      <span
        class="material-symbols-outlined text-[20px] shrink-0"
        :style="{ color: 'var(--color-outline)' }"
      >chevron_right</span>
    </div>
  </button>
</template>
