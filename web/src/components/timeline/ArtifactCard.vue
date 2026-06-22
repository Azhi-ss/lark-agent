<script setup>
import { computed } from 'vue'

/**
 * ArtifactCard —— 渲染 artifact timeline item。
 *
 * props:
 *   - id:        timeline item id（emit 时回传，供集成层定位）
 *   - artifact:  AgentArtifact { artifact_type, title, summary, payload }
 *   - isLatest:  是否为最新 artifact（最新 → 紫色强调边框 + 阴影 + 「最新」徽标）
 *
 * emits（全部透传给 ConversationTimeline）：
 *   - openArtifact(id)            点击头部「查看完整」/展开详情
 *   - locate({ id, index, replacement })  document_edits：定位到某条替换对应的 block
 *   - exportSolution(id)          solution：导出 .md
 *   - accept(id)                  采纳该 artifact
 *   - reject(id)                  忽略该 artifact
 *
 * 纯展示 + emit，不调任何 API。block_id 解析由集成层在 locate 回调里完成
 * （artifact 自身不带 block_id，与 AgentPane replacementLocations 模型一致）。
 */
const props = defineProps({
  id: { type: [Number, String], required: true },
  artifact: {
    type: Object,
    required: true,
    validator: (v) =>
      v &&
      (v.artifact_type === 'document_edits' || v.artifact_type === 'solution'),
  },
  isLatest: { type: Boolean, default: false },
})

const emit = defineEmits([
  'openArtifact',
  'locate',
  'exportSolution',
  'accept',
  'reject',
])

// action payload 与 drawer DocumentEditsArtifact.vue 对齐为 { pattern, index }，
// 让 App.vue 的 onArtifactLocate/Accept/Reject 单一 handler 同时服务 timeline 与 drawer 两条链路。
function actionPayload(i) {
  const r = replacements.value[i] || {}
  return { pattern: r.pattern, index: i }
}

const isDocEdits = computed(
  () => props.artifact.artifact_type === 'document_edits',
)
const title = computed(
  () => props.artifact.title || (isDocEdits.value ? '修改建议' : '方案'),
)
const summary = computed(() => props.artifact.summary || '')

// document_edits payload.replacements
const replacements = computed(() => {
  const p = props.artifact.payload
  return Array.isArray(p?.replacements) ? p.replacements : []
})

// solution payload.markdown
const markdown = computed(() => {
  const p = props.artifact.payload
  return typeof p?.markdown === 'string' ? p.markdown : ''
})

function truncate(s, n) {
  if (!s) return ''
  return s.length > n ? s.slice(0, n) + '…' : s
}

function onLocate(index, replacement) {
  emit('locate', { id: props.id, index, pattern: replacement?.pattern })
}
</script>

<template>
  <div
    class="rounded-lg overflow-hidden fade-in"
    :style="
      isLatest
        ? {
            background: 'var(--color-surface)',
            border: '1px solid rgba(99, 14, 212, 0.3)',
            boxShadow: '0 4px 12px rgba(99, 14, 212, 0.06)',
          }
        : {
            background: 'var(--color-surface)',
            border: '1px solid var(--color-outline-variant)',
          }
    "
  >
    <!-- 头部 -->
    <div
      class="px-4 py-2.5 flex items-center gap-2"
      :style="{
        background: 'rgba(124, 58, 237, 0.05)',
        borderBottom: '1px solid var(--color-outline-variant)',
      }"
    >
      <span
        class="material-symbols-outlined text-[18px] shrink-0"
        :style="{ color: 'var(--color-primary)' }"
        >{{ isDocEdits ? 'edit_note' : 'article' }}</span
      >
      <span
        class="text-[13px] font-semibold truncate"
        :style="{ color: 'var(--color-on-surface)' }"
        >{{ title }}</span
      >
      <span
        v-if="summary"
        class="px-2 py-0.5 rounded-sm text-[11px] shrink-0"
        :style="{
          background: 'rgba(99, 14, 212, 0.1)',
          color: 'var(--color-primary)',
        }"
        >{{ summary }}</span
      >
      <span
        v-if="isLatest"
        class="ml-auto px-2 py-0.5 rounded-sm text-[11px] shrink-0 flex items-center gap-1"
        :style="{
          background: 'var(--color-primary)',
          color: 'var(--color-on-primary)',
        }"
      >
        <span class="material-symbols-outlined text-[13px]">bolt</span>
        最新
      </span>
    </div>

    <!-- document_edits：替换列表 -->
    <div
      v-if="isDocEdits"
      class="flex flex-col max-h-[320px] overflow-y-auto"
    >
      <div
        v-if="replacements.length === 0"
        class="px-4 py-3 text-[12px]"
        :style="{ color: 'var(--color-on-surface-variant)' }"
      >
        无替换建议
      </div>
      <div
        v-for="(r, i) in replacements"
        :key="i"
        class="px-4 py-2.5 border-b last:border-b-0"
        :style="{ borderColor: 'var(--color-outline-variant)' }"
      >
        <div class="flex items-center gap-2 mb-1">
          <span
            class="text-[12px] font-semibold truncate"
            :style="{ color: 'var(--color-on-surface)' }"
            >{{ r.reason || `建议 ${i + 1}` }}</span
          >
        </div>
        <div
          class="text-[12px] mb-2"
          style="font-family: 'JetBrains Mono', ui-monospace, monospace"
          :style="{ color: 'var(--color-on-surface-variant)' }"
        >
          匹配片段：{{ truncate(r.pattern, 80) }}
        </div>
        <div class="flex justify-end">
          <button
            @click="onLocate(i, r)"
            class="px-3 py-1 rounded transition-colors text-[13px] flex items-center gap-1"
            :style="{
              background: 'var(--color-primary)',
              color: 'var(--color-on-primary)',
            }"
          >
            <span class="material-symbols-outlined text-[16px]">my_location</span>
            定位到文档
          </button>
        </div>
      </div>
    </div>

    <!-- solution：markdown 预览 -->
    <div
      v-else
      class="p-4 max-h-[420px] overflow-y-auto whitespace-pre-wrap text-[13px]"
      style="font-family: 'JetBrains Mono', ui-monospace, monospace"
      :style="{ color: 'var(--color-on-surface)' }"
    >{{ markdown || '（空方案）' }}</div>

    <!-- 底部操作条 -->
    <div
      class="px-4 py-2.5 flex items-center justify-end gap-2"
      :style="{
        background: 'var(--color-surface-container-lowest)',
        borderTop: '1px solid var(--color-outline-variant)',
      }"
    >
      <button
        @click="emit('openArtifact', id)"
        class="px-3 py-1 rounded text-[13px] transition-colors flex items-center gap-1"
        :style="{
          background: 'var(--color-surface-container-high)',
          color: 'var(--color-on-surface-variant)',
        }"
      >
        <span class="material-symbols-outlined text-[16px]">unfold_more</span>
        查看完整
      </button>

      <button
        v-if="!isDocEdits"
        @click="emit('exportSolution', id)"
        class="px-3 py-1 rounded text-[13px] font-medium transition-colors flex items-center gap-1"
        :style="{
          background: 'var(--color-secondary)',
          color: 'var(--color-on-secondary)',
        }"
      >
        <span class="material-symbols-outlined text-[16px]">download</span>
        导出 .md
      </button>

      <button
        @click="emit('reject', actionPayload(0))"
        :disabled="!isLatest"
        :title="!isLatest ? '旧版本只读' : ''"
        class="px-3 py-1 rounded text-[13px] transition-colors border disabled:opacity-40 disabled:cursor-not-allowed"
        :style="{
          background: 'transparent',
          borderColor: 'var(--color-outline-variant)',
          color: 'var(--color-on-surface-variant)',
        }"
      >
        忽略
      </button>

      <button
        @click="emit('accept', actionPayload(0))"
        :disabled="!isLatest"
        :title="!isLatest ? '旧版本只读' : ''"
        class="px-3 py-1 rounded text-[13px] font-medium transition-colors flex items-center gap-1 disabled:opacity-40 disabled:cursor-not-allowed"
        :style="{
          background: 'var(--color-primary)',
          color: 'var(--color-on-primary)',
        }"
      >
        <span class="material-symbols-outlined text-[16px]">check</span>
        采纳
      </button>
    </div>
  </div>
</template>
