<script setup>
import { ref, computed } from 'vue'
import { loadDoc, chatAgent, applyEdits, exportDoc } from './api.js'
import { textToBlockXml } from './blockXml.js'
import {
  onBlocksChanged as updateBlocksChanged,
  onChangeBlockKind as updateBlockKind,
  onMergeBlocks as mergeBlocks,
  onSplitBlock as splitBlock,
} from './appBlockHandlers.js'
import { recordRecent, listRecent, removeRecent } from './recentDocs.js'
import TopBar from './components/TopBar.vue'
import DocPane from './components/DocPane.vue'
import AgentPane from './components/AgentPane.vue'
import AppFooter from './components/AppFooter.vue'
import WorkspaceView from './components/WorkspaceView.vue'
import SettingsModal from './components/SettingsModal.vue'
import AboutModal from './components/AboutModal.vue'
import DocSearchPanel from './components/DocSearchPanel.vue'
import { createTimeline, mapSseEvent } from './composables/useTimeline.js'
import ArtifactDrawer from './components/artifact/ArtifactDrawer.vue'

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
// P3：统一 timeline 取代散落的 agentText / agentThinking / replacements / replacementLocations。
// timelineItems 单独导出为顶层 ref，模板自动解包；脚本内通过 timeline.* 调用 push/reset。
const timeline = createTimeline()
const timelineItems = timeline.items
const running = ref(false)
const applyStatus = ref('')
const applying = ref(false)

// artifact drawer：drawerArtifact 当前审阅的 artifact；drawerIsLatest 是否为 timeline 中最后一个 artifact
const drawerArtifact = ref(null)
const drawerIsLatest = ref(false)

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

function currentDocTitle() {
  const titleBlock = blocks.value.find((b) => b.kind === 'title')
  if (titleBlock?.text?.trim()) return titleBlock.text.trim()
  return docMeta.value.document_id || 'document'
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
  timeline.reset()
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

// document_edits artifact 落到 timeline 后的业务副作用：
// 清掉旧 suggestion，按 pattern 重新定位挂载到 blocks（与 P2 done 分支语义一致）。
function onDocumentEdits(payload) {
  const reps = payload?.replacements || []
  // 清掉旧 suggestion，重新按 pattern 定位挂载
  for (const b of blocks.value) b.suggestion = null
  reps.forEach((r) => {
    const bid = locateBlock(r.pattern)
    if (bid === null || bid === undefined) return
    const blk = blocks.value.find((b) => b.block_id === bid)
    if (blk) {
      // suggestion.content 是 agent 给的纯文本，接受时再转 xml（见 acceptSuggestion）。
      blk.suggestion = {
        content: r.content,
        reason: r.reason || '',
        state: 'pending',
      }
    }
  })
}

// editor 模式无 solution artifact，留空。
function onSolution(_payload) {}

async function onChat() {
  if (!loaded.value || running.value) return
  running.value = true
  applyStatus.value = ''
  timeline.reset()
  timeline.pushUser(instruction.value)
  try {
    // P3：SSE 产品语义事件统一走 mapSseEvent → timeline。
    // artifact 事件先回调业务副作用（onDocumentEdits 挂载 suggestion），再 push 进 timeline 展示。
    await chatAgent(docUrl.value, instruction.value, (ev) =>
      mapSseEvent(ev, timeline, { onDocumentEdits, onSolution }),
    )
  } catch (e) {
    // 网络层抛错（非 SSE error 事件）→ timeline + footer 双通道提示
    timeline.pushError(e.message)
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
}

// 拆块：光标处把原块 text 切成 textBefore（留原块）+ textAfter（新块，同 kind）。
// 两块均 edited + pending_xml。cursorPos 由 DocPane 传入仅供参考，拆分结果以 textBefore/textAfter 为准。
function onSplitBlock(blockId, cursorPos, textBefore, textAfter) {
  blocks.value = splitBlock(blocks.value, blockId, cursorPos, textBefore, textAfter, textToBlockXml)
}

// 合块：current.text 追加到 previous.text 末尾并移除 current；previous edited + pending_xml。
// 注意：pending_xml 必须按合并后文本重新生成，否则 onApply 会把空 pending_xml 当 block_delete。
function onMergeBlocks(currentBlockId, previousBlockId) {
  blocks.value = mergeBlocks(blocks.value, currentBlockId, previousBlockId, textToBlockXml)
}

// 改块类型：同时更新 kind 与 text，按新 kind 生成 pending_xml，edited=true。
function onChangeBlockKind(blockId, newKind, cleanedText) {
  blocks.value = updateBlockKind(blocks.value, blockId, newKind, cleanedText, textToBlockXml)
}

// 批量更新块文本：updates = [{block_id, text}, ...]（兼容 blockId）。
// 每块 text 落库 + 按 kind 生成 pending_xml + edited=true。
function onBlocksChanged(updates) {
  blocks.value = updateBlocksChanged(blocks.value, updates, textToBlockXml)
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

// ===== artifact drawer / timeline 事件处理 =====
// openArtifact：打开 drawer 审阅某 artifact。id 来自 ConversationTimeline 透传；
// 在 timeline 中按 id 查找 artifact item，id 缺失时回退到最后一个 artifact。
// isLatest 取该 item 是否为 timeline 中最后一个 artifact（useTimeline.pushArtifact 已维护此标记）。
function openArtifact(id) {
  const artifactItems = timelineItems.value.filter((it) => it.kind === 'artifact')
  let item = artifactItems.find((it) => it.id === id)
  if (!item && artifactItems.length > 0) item = artifactItems[artifactItems.length - 1]
  if (!item) return
  drawerArtifact.value = item.artifact
  drawerIsLatest.value = !!item.isLatest
}

function closeDrawer() {
  drawerArtifact.value = null
}

// drawer / timeline locate：pattern → blockId → 滚动定位（复用 locateBlock + DocPane.scrollToBlock）
function onArtifactLocate(payload) {
  const bid = locateBlock(payload?.pattern)
  if (bid === null || bid === undefined) return
  docPaneRef.value?.scrollToBlock(bid)
}

// drawer / timeline accept：pattern → blockId → 复用 acceptSuggestion
function onArtifactAccept(payload) {
  const bid = locateBlock(payload?.pattern)
  if (bid === null || bid === undefined) return
  acceptSuggestion(bid)
}

// drawer / timeline reject：pattern → blockId → 复用 rejectSuggestion
function onArtifactReject(payload) {
  const bid = locateBlock(payload?.pattern)
  if (bid === null || bid === undefined) return
  rejectSuggestion(bid)
}

// drawer / timeline writeback：复用 onApply（写回所有 edited 的块）
function onArtifactWriteback() {
  onApply()
}

// action_required 未知 reason 的通用确认（editor 模式仅 writeback_confirmation，故此分支不会触发）
function onAction() {}

function onQuickAction(text) {
  instruction.value = text
}

function onOpenExternal() {
  if (docUrl.value) {
    window.open(docUrl.value, '_blank', 'noopener')
  }
}

async function onExportDoc(format) {
  if (!loaded.value || !docUrl.value) return
  const normalized = format === 'docx' ? 'docx' : 'md'
  applyStatus.value = `导出 ${normalized.toUpperCase()} 中...`
  try {
    await exportDoc(docUrl.value, normalized, currentDocTitle())
    applyStatus.value = `已导出 ${normalized.toUpperCase()} 到本地`
  } catch (e) {
    applyStatus.value = '导出失败: ' + e.message
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
          @edit-block="editBlock"
          @load-recent="loadRecent"
          @remove-recent="onRemoveRecent"
          @open-search="searchOpen = true"
          @export-doc="onExportDoc"
          @split-block="onSplitBlock"
          @merge-blocks="onMergeBlocks"
          @change-block-kind="onChangeBlockKind"
          @blocks-changed="onBlocksChanged"
        />
        <AgentPane
          :loaded="loaded"
          :running="running"
          :instruction="instruction"
          :timeline-items="timelineItems"
          @update:instruction="instruction = $event"
          @chat="onChat"
          @quick-action="onQuickAction"
          @open-artifact="openArtifact"
          @locate="onArtifactLocate"
          @accept="onArtifactAccept"
          @reject="onArtifactReject"
          @writeback="onArtifactWriteback"
          @action="onAction"
        />
        <!-- P3：artifact drawer（Teleport 到 body，仅 editor 模式实例化） -->
        <ArtifactDrawer
          :open="!!drawerArtifact"
          :artifact="drawerArtifact"
          :is-latest="drawerIsLatest"
          @close="closeDrawer"
          @locate="onArtifactLocate"
          @accept="onArtifactAccept"
          @reject="onArtifactReject"
          @writeback="onArtifactWriteback"
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
