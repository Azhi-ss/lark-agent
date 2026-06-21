<script setup>
import { ref, computed } from 'vue'
import { loadDoc, chatAgent, applyEdits } from './api.js'
import TopBar from './components/TopBar.vue'
import DocPane from './components/DocPane.vue'
import AgentPane from './components/AgentPane.vue'
import AppFooter from './components/AppFooter.vue'
import WorkspaceView from './components/WorkspaceView.vue'
import SettingsModal from './components/SettingsModal.vue'
import AboutModal from './components/AboutModal.vue'
import DocSearchPanel from './components/DocSearchPanel.vue'

const activeMode = ref('editor') // 'editor' | 'workspace'
const settingsOpen = ref(false)
const helpOpen = ref(false)
const searchOpen = ref(false)

// 单文档模式：搜索导入取第一份填 URL 并加载
function onImportToEditor(urls) {
  if (!urls || urls.length === 0) return
  if (urls.length > 1) {
    // 单文档模式仅导入第一份，提示用户
    applyStatus.value = `单文档模式仅导入第一份（共选 ${urls.length} 份）`
    setTimeout(() => (applyStatus.value = ''), 3000)
  }
  docUrl.value = urls[0]
  searchOpen.value = false
  onLoad()
}

const docUrl = ref('https://dptechnology.feishu.cn/wiki/OWAIwHYLJiyEHjkJvRAcEmKnn7y')
const markdown = ref('')
const blocks = ref([])
const docMeta = ref({ document_id: '', revision_id: 0, block_count: 0 })
const loading = ref(false)
const loadError = ref('')

const instruction = ref('提炼本周（最近一篇）核心要点，在文末追加"## 本周要点"摘要段落。')
const agentText = ref('')
const agentThinking = ref('')
const replacements = ref([])
// 每个 replacement 定位到的 block_id（无法定位为 null）；用于 AgentPane 摘要分组
const replacementLocations = ref([])
const running = ref(false)
const applyStatus = ref('')
const applying = ref(false)

const docPaneRef = ref(null)

const loaded = computed(() => markdown.value.length > 0)
const editedCount = computed(() => blocks.value.filter((b) => b.edited).length)

async function onLoad() {
  if (loading.value) return
  loading.value = true
  loadError.value = ''
  markdown.value = ''
  blocks.value = []
  replacements.value = []
  replacementLocations.value = []
  agentText.value = ''
  agentThinking.value = ''
  applyStatus.value = ''
  try {
    const data = await loadDoc(docUrl.value)
    markdown.value = data.markdown
    docMeta.value = {
      document_id: data.document_id,
      revision_id: data.revision_id,
      block_count: data.block_count,
    }
    // 后端契约 §3.1：blocks 数组。map 成前端可编辑结构（edited:false, suggestion:null）。
    blocks.value = (data.blocks || []).map((b) => ({
      block_id: b.block_id ?? '',
      kind: b.kind,
      text: b.text ?? '',
      markdown: b.markdown ?? '',
      original: b.original ?? b.markdown ?? '',
      level: b.level ?? 0,
      edited: false,
      suggestion: null,
    }))
  } catch (e) {
    loadError.value = e.message
  } finally {
    loading.value = false
  }
}

// §5.1 pattern -> block_id 定位：先精确子串，后归一化去空白
function locateBlock(pattern) {
  if (!pattern) return null
  for (const b of blocks.value) {
    if (b.markdown.includes(pattern)) return b.block_id
  }
  const norm = (s) => s.replace(/\s+/g, '')
  const np = norm(pattern)
  if (!np) return null
  for (const b of blocks.value) {
    if (norm(b.markdown).includes(np)) return b.block_id
  }
  return null
}

async function onChat() {
  if (!loaded.value || running.value) return
  running.value = true
  agentText.value = ''
  agentThinking.value = ''
  replacements.value = []
  replacementLocations.value = []
  applyStatus.value = ''
  try {
    await chatAgent(markdown.value, instruction.value, (ev) => {
      if (ev.type === 'thinking') {
        agentThinking.value += ev.data.text
      } else if (ev.type === 'text') {
        agentText.value += ev.data.text
      } else if (ev.type === 'done') {
        const reps = ev.data.replacements || []
        replacements.value = reps
        // 清掉旧 suggestion，重新按 pattern 定位挂载
        for (const b of blocks.value) b.suggestion = null
        const locs = reps.map((r) => locateBlock(r.pattern))
        replacementLocations.value = locs
        reps.forEach((r, i) => {
          const bid = locs[i]
          if (bid === null || bid === undefined) return
          const blk = blocks.value.find((b) => b.block_id === bid)
          if (blk) {
            blk.suggestion = { content: r.content, reason: r.reason || '', state: 'pending' }
          }
        })
      } else if (ev.type === 'error') {
        applyStatus.value = '错误: ' + ev.data.message
      }
    })
  } catch (e) {
    applyStatus.value = '错误: ' + e.message
  } finally {
    running.value = false
  }
}

function findBlock(blockId) {
  return blocks.value.find((b) => b.block_id === blockId)
}

// §5.2 接受/拒绝/手编/还原语义
function acceptSuggestion(blockId) {
  const b = findBlock(blockId)
  if (!b || !b.suggestion) return
  b.markdown = b.suggestion.content
  b.edited = true
  b.suggestion.state = 'accepted'
}

function rejectSuggestion(blockId) {
  const b = findBlock(blockId)
  if (!b || !b.suggestion) return
  b.suggestion.state = 'rejected'
}

function editBlock(blockId, newMarkdown) {
  const b = findBlock(blockId)
  if (!b) return
  b.markdown = newMarkdown
  b.edited = true
}

function resetBlock(blockId) {
  const b = findBlock(blockId)
  if (!b) return
  b.markdown = b.original
  b.edited = false
  b.suggestion = null
}

async function onApply() {
  const edited = blocks.value.filter((b) => b.edited)
  if (edited.length === 0 || applying.value) return
  applying.value = true
  applyStatus.value = '写回中...'
  try {
    const edits = edited.map((b) => ({ block_id: b.block_id, content: b.markdown }))
    const res = await applyEdits(docUrl.value, edits, docMeta.value.revision_id)
    if (res.conflict) {
      applyStatus.value = '文档已被修改，请重新加载'
    } else if (res.ok) {
      applyStatus.value = `已写回飞书（${res.count ?? edited.length} 块）`
      // 清 edited 标记，并把 original 推进到刚写回的内容（还原以新基线为准）
      for (const b of edited) {
        b.edited = false
        b.original = b.markdown
      }
      // 已接受的建议已落库，清掉卡片
      for (const b of blocks.value) {
        if (b.suggestion && b.suggestion.state === 'accepted') b.suggestion = null
      }
      if (res.final_revision_id) {
        docMeta.value = { ...docMeta.value, revision_id: res.final_revision_id }
      }
    } else {
      const failed = (res.results || []).filter((r) => !r.ok).length
      applyStatus.value = `部分失败：${failed} 块`
    }
  } catch (e) {
    applyStatus.value = '写回失败: ' + e.message
  } finally {
    applying.value = false
  }
}

function onLocate(blockId) {
  if (blockId === null || blockId === undefined) return
  docPaneRef.value?.scrollToBlock(blockId)
}

function onQuickAction(text) {
  instruction.value = text
}

function onOpenExternal() {
  if (docUrl.value) {
    window.open(docUrl.value, '_blank', 'noopener')
  }
}
</script>

<template>
  <div class="h-screen flex flex-col overflow-hidden">
    <TopBar
      v-model="docUrl"
      :loading="loading"
      @load="onLoad"
      @open-settings="settingsOpen = true"
      @open-help="helpOpen = true"
      @open-search="searchOpen = true"
    >
      <template #tabs>
        <div
          class="flex items-center rounded-lg p-0.5"
          :style="{ background: 'var(--color-surface-container)' }"
        >
          <button
            @click="activeMode = 'editor'"
            class="px-3 py-1 rounded-md text-[13px] font-medium transition-colors"
            :style="{
              background:
                activeMode === 'editor'
                  ? 'var(--color-surface)'
                  : 'transparent',
              color:
                activeMode === 'editor'
                  ? 'var(--color-primary)'
                  : 'var(--color-on-surface-variant)',
              boxShadow:
                activeMode === 'editor'
                  ? '0 1px 2px rgba(0,0,0,0.05)'
                  : 'none',
            }"
          >
            📝 单文档编辑
          </button>
          <button
            @click="activeMode = 'workspace'"
            class="px-3 py-1 rounded-md text-[13px] font-medium transition-colors"
            :style="{
              background:
                activeMode === 'workspace'
                  ? 'var(--color-surface)'
                  : 'transparent',
              color:
                activeMode === 'workspace'
                  ? 'var(--color-primary)'
                  : 'var(--color-on-surface-variant)',
              boxShadow:
                activeMode === 'workspace'
                  ? '0 1px 2px rgba(0,0,0,0.05)'
                  : 'none',
            }"
          >
            🧩 方案构建
          </button>
        </div>
      </template>
    </TopBar>

    <Transition name="fade" mode="out-in">
      <main
        v-if="activeMode === 'editor'"
        key="editor"
        class="flex-1 flex overflow-hidden"
      >
        <DocPane
          ref="docPaneRef"
          :loaded="loaded"
          :doc-meta="docMeta"
          :blocks="blocks"
          :load-error="loadError"
          @open-external="onOpenExternal"
          @accept-suggestion="acceptSuggestion"
          @reject-suggestion="rejectSuggestion"
          @reset-block="resetBlock"
          @edit-block="editBlock"
        />
        <AgentPane
          :loaded="loaded"
          :running="running"
          :instruction="instruction"
          :agent-text="agentText"
          :agent-thinking="agentThinking"
          :replacements="replacements"
          :replacement-locations="replacementLocations"
          @update:instruction="instruction = $event"
          @chat="onChat"
          @quick-action="onQuickAction"
          @locate="onLocate"
        />
      </main>
      <WorkspaceView v-else key="workspace" />
    </Transition>

    <AppFooter
      v-if="activeMode === 'editor'"
      :pending-count="editedCount"
      :apply-status="applyStatus"
      :applying="applying"
      @apply="onApply"
    />

    <SettingsModal
      :open="settingsOpen"
      @close="settingsOpen = false"
      @saved="(cfg) => (settingsOpen = false)"
    />
    <AboutModal :open="helpOpen" @close="helpOpen = false" />

    <!-- 搜索导入浮层（单文档编辑模式） -->
    <Teleport to="body">
      <div
        v-if="searchOpen"
        class="fixed inset-0 z-[100] flex items-start justify-center pt-20"
        :style="{ background: 'rgba(0,0,0,0.4)' }"
        @click.self="searchOpen = false"
      >
        <div
          class="w-[560px] max-w-[92vw] max-h-[80vh] rounded-xl shadow-2xl overflow-hidden flex flex-col"
          :style="{
            background: 'var(--color-surface)',
            border: '1px solid var(--color-outline-variant)',
          }"
        >
          <div
            class="px-6 py-4 flex items-center justify-between border-b shrink-0"
            :style="{ borderColor: 'var(--color-outline-variant)' }"
          >
            <h3
              class="text-lg font-semibold flex items-center gap-2"
              style="font-family: 'Hanken Grotesk', sans-serif"
              :style="{ color: 'var(--color-on-surface)' }"
            >
              <span class="material-symbols-outlined" :style="{ color: 'var(--color-primary)' }">search</span>
              搜索飞书文档
            </h3>
            <button
              aria-label="关闭"
              class="p-1 rounded-full transition-colors hover:bg-[var(--color-surface-container-high)]"
              :style="{ color: 'var(--color-on-surface-variant)' }"
              @click="searchOpen = false"
            >
              <span class="material-symbols-outlined">close</span>
            </button>
          </div>
          <div class="p-4 flex-1 min-h-0 overflow-hidden flex flex-col">
            <DocSearchPanel @import="onImportToEditor" />
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.18s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
