<script setup>
import TimelineMessage from './TimelineMessage.vue'
import StatusStep from './StatusStep.vue'
import ThinkingSummary from './ThinkingSummary.vue'
import ArtifactCard from './ArtifactCard.vue'

/**
 * ConversationTimeline —— 通用对话/产物时间线容器。
 *
 * props:
 *   - items:   TimelineItem[]（来自 useTimeline().items）
 *   - running: 是否仍在流式运行（传给 ThinkingSummary 控制旋转态）
 *
 * emits（透传子组件 emit + 内联 action_required 的确认动作）：
 *   - openArtifact(id)                 透传 ArtifactCard
 *   - action(id)                       action_required 未知 reason 的通用确认
 *   - locate({ id, index, replacement })  透传 ArtifactCard（document_edits 定位 block）
 *   - accept(id)                       透传 ArtifactCard（采纳 artifact）
 *   - reject(id | undefined)           透传 ArtifactCard / action_required 取消
 *   - writeback(id | undefined)        action_required reason=writeback_confirmation 的确认
 *   - exportSolution(id)               透传 ArtifactCard（solution 导出 .md）
 *   - overwriteSolution(id | undefined)  action_required reason=overwrite_solution_confirmation 的确认
 *
 * 纯展示 + emit，不直接调 API。error / complete / action_required 内联渲染。
 */
defineProps({
  items: { type: Array, default: () => [] },
  running: { type: Boolean, default: false },
})

const emit = defineEmits([
  'openArtifact',
  'action',
  'locate',
  'accept',
  'reject',
  'writeback',
  'exportSolution',
  'overwriteSolution',
  'dismiss',
])

// action_required 文案与确认 emit 映射
const ACTION_META = {
  writeback_confirmation: {
    icon: 'edit_note',
    title: '需要确认写回',
    desc: 'Agent 准备将修改写回飞书文档，请确认。',
    confirmText: '确认写回',
    confirmEmit: 'writeback',
    confirmStyle: { background: 'var(--color-secondary)', color: 'var(--color-on-secondary)' },
  },
  overwrite_solution_confirmation: {
    icon: 'warning',
    title: '即将覆盖现有方案',
    desc: '继续将覆盖当前方案，此操作不可撤销。',
    confirmText: '覆盖方案',
    confirmEmit: 'overwriteSolution',
    confirmStyle: { background: 'var(--color-error)', color: 'var(--color-on-primary)' },
  },
  workspace_file_apply: {
    icon: 'description',
    title: '需要应用文件编辑',
    desc: 'Agent 准备将建议内容写入本地工作区文件，请确认。',
    confirmText: '应用文件',
    confirmEmit: 'action',
    confirmStyle: { background: 'var(--color-primary)', color: 'var(--color-on-primary)' },
  },
}

function metaFor(reason) {
  return ACTION_META[reason] || {
    icon: 'help',
    title: '需要确认',
    desc: 'Agent 需要你确认后再继续。',
    confirmText: '确认',
    confirmEmit: 'action',
    confirmStyle: { background: 'var(--color-primary)', color: 'var(--color-on-primary)' },
  }
}

function confirmAction(item) {
  const meta = metaFor(item.reason)
  // 已知 reason 回传 item.id 便于集成层定位上下文；通用 action 同样带 id
  emit(meta.confirmEmit, item.id)
}

function cancelAction(item) {
  // action_required 的「取消」与 artifact suggestion 的「拒绝」是两件事，
  // 不复用 reject 通道。dismiss 通知集成层移除/收起该 action_required 卡片。
  item.dismissed = true
  emit('dismiss', item.id)
}
</script>

<template>
  <div class="flex flex-col gap-3">
    <template v-for="item in items" :key="item.id">
      <!-- user / assistant_text -->
      <TimelineMessage
        v-if="item.kind === 'user' || item.kind === 'assistant_text'"
        :item="item"
        class="fade-in"
      />

      <!-- status -->
      <StatusStep
        v-else-if="item.kind === 'status'"
        :label="item.label"
        :state="item.state"
        class="fade-in"
      />

      <!-- thinking_summary -->
      <ThinkingSummary
        v-else-if="item.kind === 'thinking_summary'"
        :text="item.text"
        :running="running"
        class="fade-in"
      />

      <!-- artifact -->
      <ArtifactCard
        v-else-if="item.kind === 'artifact'"
        :id="item.id"
        :artifact="item.artifact"
        :is-latest="item.isLatest"
        @open-artifact="emit('openArtifact', item.id)"
        @locate="emit('locate', $event)"
        @export-solution="emit('exportSolution', $event)"
        @accept="emit('accept', $event)"
        @reject="emit('reject', $event)"
        class="fade-in"
      />

      <!-- action_required（内联） -->
      <div
        v-else-if="item.kind === 'action_required' && !item.dismissed"
        class="rounded-lg border fade-in p-4 flex items-start gap-3"
        :style="{
          background: 'var(--color-surface)',
          borderColor: 'var(--color-outline-variant)',
        }"
      >
        <span
          class="material-symbols-outlined text-[20px] shrink-0 mt-0.5"
          :style="{ color: 'var(--color-primary)' }"
          >{{ metaFor(item.reason).icon }}</span
        >
        <div class="flex-1 min-w-0">
          <p
            class="text-[14px] font-semibold"
            :style="{ color: 'var(--color-on-surface)' }"
          >
            {{ metaFor(item.reason).title }}
          </p>
          <p
            class="text-[12px] mt-0.5"
            :style="{ color: 'var(--color-on-surface-variant)' }"
          >
            {{ metaFor(item.reason).desc }}
          </p>
          <div class="flex justify-end gap-2 mt-3">
            <button
              @click="cancelAction(item)"
              class="px-3 py-1 rounded text-[13px] transition-colors border"
              :style="{
                background: 'transparent',
                borderColor: 'var(--color-outline-variant)',
                color: 'var(--color-on-surface-variant)',
              }"
            >
              取消
            </button>
            <button
              @click="confirmAction(item)"
              class="px-3 py-1 rounded text-[13px] font-medium transition-colors flex items-center gap-1"
              :style="metaFor(item.reason).confirmStyle"
            >
              <span class="material-symbols-outlined text-[16px]">check</span>
              {{ metaFor(item.reason).confirmText }}
            </button>
          </div>
        </div>
      </div>

      <!-- error（内联） -->
      <div
        v-else-if="item.kind === 'error'"
        class="rounded-lg border fade-in px-4 py-3 flex items-center gap-2"
        :style="{
          background: 'var(--color-danger-surface)',
          borderColor: 'var(--color-outline-variant)',
        }"
      >
        <span
          class="material-symbols-outlined text-[18px] shrink-0"
          :style="{ color: 'var(--color-danger-text)' }"
          >error</span
        >
        <p
          class="text-[13px]"
          :style="{ color: 'var(--color-danger-text)' }"
        >{{ item.message }}</p>
      </div>

      <!-- complete（内联） -->
      <div
        v-else-if="item.kind === 'complete'"
        class="flex items-center gap-2 fade-in py-1"
      >
        <span
          class="material-symbols-outlined text-[16px]"
          :style="{ color: 'var(--color-success-text)' }"
          >check_circle</span
        >
        <span
          class="text-[13px]"
          :style="{ color: 'var(--color-on-surface-variant)' }"
          >处理完成</span
        >
      </div>
    </template>
  </div>
</template>
