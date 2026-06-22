<script setup>
import { ref, computed } from 'vue'
import { loadDoc, chatAgent, applyEdits } from './api.js'
import { textToBlockXml } from './blockXml.js'
import { recordRecent, listRecent, removeRecent } from './recentDocs.js'
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
// P2：blocks 是唯一真相源，不再维护整篇 markdown。
// block 结构：{block_id, kind, text, raw_xml, level, original_text, original_xml,
//              edited, suggestion, pending_xml}
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

const loaded = computed(() => blocks.value.length > 0)
const editedCount = computed(() => blocks.value.filter((b) => b.edited).length)

// 最近访问文档（localStorage 持久化），加载成功后记录并刷新
const recentDocs = ref(listRecent())

function docTitleFromLoad(data) {
  // 优先取首个 title 块文本，回退 document_id（P2 不再有整篇 markdown）
  const titleBlock = (data.blocks || []).find((b) => b.kind === 'title')
  if (titleBlock?.text?.trim()) return titleBlock.text.trim()
  return data.document_id || ''
}

function loadRecent(url) {
  if (!url || loading.value) return
  docUrl.value = url
  onLoad()
}

function onRemoveRecent(url) {
  removeRecent(url)
  recentDocs.value = listRecent()
}

async function onLoad() {
  if (loading.value) return
  loading.value = true
  loadError.value = ''
  blocks.value = []
  replacements.value = []
  replacementLocations.value = []
  agentText.value = ''
  agentThinking.value = ''
  applyStatus.value = ''
  try {
    const data = await loadDoc(docUrl.value)
    docMeta.value = {
      document_id: data.document_id,
      revision_id: data.revision_id,
      block_count: (data.blocks || []).length,
    }
    // 后端契约 §3.2：blocks 每项 {block_id, kind, text, raw_xml, level}。
    // map 成前端可编辑结构：text 作编辑初始值，raw_xml/original_text/original_xml 保留作还原基线。
    blocks.value = (data.blocks || []).map((b) => ({
      block_id: b.block_id ?? '',
      kind: b.kind,
      text: b.text ?? '',
      raw_xml: b.raw_xml ?? '',
      level: b.level ?? 0,
      // 还原基线：写回前原始文本与原始 xml（写回后 block-id 会变，重 load 会刷新这两项）
      original_text: b.text ?? '',
      original_xml: b.raw_xml ?? '',
      edited: false,
      suggestion: null,
      pending_xml: null,
      deleting: false,
    }))
    // 加载成功 → 记录到最近访问（localStorage 持久化）
    recordRecent(docUrl.value, docTitleFromLoad(data))
    recentDocs.value = listRecent()
  } catch (e) {
    loadError.value = e.message
  } finally {
    loading.value = false
  }
}

// §5.1 pattern -> block_id 定位：先在块 text 里精确子串，后归一化去空白。
// 注意：P2 定位基于块纯文本 text（agent 给的 pattern 落在单块 text 内）。
function locateBlock(pattern) {
  if (!pattern) return null
  for (const b of blocks.value) {
    if (b.text.includes(pattern)) return b.block_id
  }
  const norm = (s) => s.replace(/\s+/g, '')
  const np = norm(pattern)
  if (!np) return null
  for (const b of blocks.value) {
    if (norm(b.text).includes(np)) return b.block_id
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
    // P2 §3.3：只传 url + instruction，不再传 markdown。
    await chatAgent(docUrl.value, instruction.value, (ev) => {
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
          // 跳过已标记删除的块：不再给将删除的块挂建议，避免 deleting + 非空 pending_xml 状态不一致
          if (blk && !blk.deleting) {
            // suggestion.content 现在是 agent 给的纯文本，接受时再转 xml（见 acceptSuggestion）。
            blk.suggestion = {
              content: r.content,
              reason: r.reason || '',
              state: 'pending',
            }
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

// §5.2 接受/拒绝/手编/还原语义。P2：编辑/接受都生成该块 xml 存 pending_xml。
function acceptSuggestion(blockId) {
  const b = findBlock(blockId)
  if (!b || !b.suggestion) return
  b.text = b.suggestion.content
  b.pending_xml = textToBlockXml(b.kind, b.text)
  b.edited = true
  b.deleting = false // 接受建议=非删除编辑，覆盖删除意图，避免 pending_xml 非空但 deleting=true 的不一致
  b.suggestion.state = 'accepted'
}

function rejectSuggestion(blockId) {
  const b = findBlock(blockId)
  if (!b || !b.suggestion) return
  b.suggestion.state = 'rejected'
}

// 手编：存 block.text=newText，按 kind 生成 xml 存 pending_xml，edited=true。
function editBlock(blockId, newText) {
  const b = findBlock(blockId)
  if (!b) return
  b.text = newText
  b.pending_xml = textToBlockXml(b.kind, newText)
  b.edited = true
  b.deleting = false // 手编=非删除编辑，覆盖删除意图，避免状态不一致
}

// 还原：text/raw_xml 恢复原始，edited=false，pending_xml=null，suggestion=null。
function resetBlock(blockId) {
  const b = findBlock(blockId)
  if (!b) return
  b.text = b.original_text
  b.raw_xml = b.original_xml
  b.edited = false
  b.pending_xml = null
  b.suggestion = null
  b.deleting = false
}

// 删除整块：置空 pending_xml（写回走 block_delete），标记 deleting + edited。
// 不立即从列表移除：保留可见（置灰+删除线）直到写回成功重 load 后自然消失。
function deleteBlock(blockId) {
  const b = findBlock(blockId)
  if (!b) return
  b.deleting = true
  b.edited = true
  b.pending_xml = ''
  b.suggestion = null
}

// §5.2 写回后重新 load 是核心修复：block-id 写回后必变（飞书硬约束），
// 必须 re-fetch 刷新 block-id + revision_id，否则下次写回用失效旧 id。
async function onApply() {
  const edited = blocks.value.filter((b) => b.edited)
  if (edited.length === 0 || applying.value) return
  applying.value = true
  applyStatus.value = '写回中...'
  try {
    // edits = [{block_id, xml: b.pending_xml}]；空 pending_xml（空文本）→ block_delete。
    const edits = edited.map((b) => ({ block_id: b.block_id, xml: b.pending_xml ?? '' }))
    const res = await applyEdits(docUrl.value, edits, docMeta.value.revision_id)
    if (res.conflict) {
      applyStatus.value = '文档已被修改，请重新加载'
    } else if (res.ok) {
      applyStatus.value = `已写回飞书（${res.count ?? edited.length} 块），正在刷新…`
      // 关键修复：重新加载刷新 block-id + revision_id（P2 §2 支柱 2）。
      await onLoad()
      applyStatus.value = `已写回飞书（${res.count ?? edited.length} 块）`
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
          :recent-docs="recentDocs"
          @open-external="onOpenExternal"
          @accept-suggestion="acceptSuggestion"
          @reject-suggestion="rejectSuggestion"
          @reset-block="resetBlock"
          @delete-block="deleteBlock"
          @edit-block="editBlock"
          @load-recent="loadRecent"
          @remove-recent="onRemoveRecent"
          @open-search="searchOpen = true"
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
