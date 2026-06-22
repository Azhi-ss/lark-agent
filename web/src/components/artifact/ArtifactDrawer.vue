<script setup>
import { computed, onMounted, onUnmounted } from 'vue'
import DocumentEditsArtifact from './DocumentEditsArtifact.vue'
import SolutionArtifact from './SolutionArtifact.vue'

/**
 * 右侧抽屉：artifact 的完整审阅形态。
 * - fixed 定位，从右滑入，宽 480px，max 92vw
 * - 遮罩点击 / ESC / 关闭按钮均 emit('close')
 * - 按 artifact_type 渲染子组件，透传子组件 emit（保持 { pattern, index } 语义）
 */
const props = defineProps({
  open: { type: Boolean, default: false },
  artifact: { type: Object, default: null }, // AgentArtifact | null
  isLatest: { type: Boolean, default: false },
})
const emit = defineEmits([
  'close',
  'locate',
  'accept',
  'reject',
  'writeback',
  'exportSolution',
  'overwriteSolution',
])

const type = computed(() => props.artifact?.artifact_type)
const title = computed(() => props.artifact?.title || '')
const summary = computed(() => props.artifact?.summary || '')
const payload = computed(() => props.artifact?.payload || null)
const headerIcon = computed(() =>
  type.value === 'solution' ? 'article' : 'edit_note',
)

function onEsc(e) {
  if (e.key === 'Escape' && props.open) emit('close')
}
onMounted(() => window.addEventListener('keydown', onEsc))
onUnmounted(() => window.removeEventListener('keydown', onEsc))
</script>

<template>
  <Teleport to="body">
    <transition name="artifact-overlay">
      <div
        v-if="open"
        class="fixed inset-0 z-50"
        :style="{ background: 'rgba(0, 0, 0, 0.4)' }"
        @click="emit('close')"
      ></div>
    </transition>
    <transition name="artifact-drawer">
      <aside
        v-if="open"
        class="fixed right-0 top-0 bottom-0 z-50 w-[480px] max-w-[92vw] flex flex-col"
        :style="{
          background: 'var(--color-surface)',
          borderLeft: '1px solid var(--color-outline-variant)',
          boxShadow: '-8px 0 24px rgba(0, 0, 0, 0.08)',
        }"
      >
        <!-- 头部 -->
        <div
          class="px-5 py-4 flex items-center gap-3 shrink-0 border-b"
          :style="{
            background: 'rgba(124, 58, 237, 0.05)',
            borderColor: 'var(--color-outline-variant)',
          }"
        >
          <span
            class="material-symbols-outlined text-[22px] shrink-0"
            :style="{ color: 'var(--color-primary)' }"
          >{{ headerIcon }}</span>
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2">
              <h3
                class="text-[15px] font-semibold truncate"
                :style="{ color: 'var(--color-on-surface)' }"
              >{{ title }}</h3>
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
              v-if="summary"
              class="text-[12px] mt-0.5 truncate"
              :style="{ color: 'var(--color-on-surface-variant)' }"
            >{{ summary }}</p>
          </div>
          <button
            type="button"
            @click="emit('close')"
            aria-label="关闭"
            class="p-1.5 rounded transition-colors hover:bg-[var(--color-surface-container)]"
            :style="{ color: 'var(--color-on-surface-variant)' }"
          >
            <span class="material-symbols-outlined text-[20px]">close</span>
          </button>
        </div>

        <!-- 内容区：子组件自管滚动，底部按钮固定 -->
        <div class="flex-1 min-h-0 flex flex-col">
          <DocumentEditsArtifact
            v-if="type === 'document_edits'"
            :payload="payload"
            :is-latest="isLatest"
            @locate="(p) => emit('locate', p)"
            @accept="(p) => emit('accept', p)"
            @reject="(p) => emit('reject', p)"
            @writeback="emit('writeback')"
          />
          <SolutionArtifact
            v-else-if="type === 'solution'"
            :payload="payload"
            :is-latest="isLatest"
            @export-solution="emit('exportSolution')"
            @overwrite-solution="emit('overwriteSolution')"
          />
          <div
            v-else
            class="p-8 text-center text-[13px]"
            :style="{ color: 'var(--color-on-surface-variant)' }"
          >
            未知 artifact 类型
          </div>
        </div>
      </aside>
    </transition>
  </Teleport>
</template>

<style scoped>
.artifact-overlay-enter-active,
.artifact-overlay-leave-active {
  transition: opacity 0.2s ease;
}
.artifact-overlay-enter-from,
.artifact-overlay-leave-to {
  opacity: 0;
}
.artifact-drawer-enter-active,
.artifact-drawer-leave-active {
  transition: transform 0.25s ease;
}
.artifact-drawer-enter-from,
.artifact-drawer-leave-to {
  transform: translateX(100%);
}
</style>
