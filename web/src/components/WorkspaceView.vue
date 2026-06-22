<script setup>
import { ref, computed } from 'vue'
import {
  loadMany,
  chatSolution,
  exportMd,
  saveWorkspace,
} from '../api.js'
import { createTimeline, mapSseEvent } from '../composables/useTimeline.js'
import DocSearchPanel from './DocSearchPanel.vue'
import ConversationTimeline from './timeline/ConversationTimeline.vue'
import ArtifactDrawer from './artifact/ArtifactDrawer.vue'

/**
 * 方案构建模式（P3 workspace 集成）：
 * - 左侧主画布：tab 切换「当前方案 / 上下文文档」。当前方案渲染 solution.markdown；
 *   上下文文档保留加载 / 搜索导入 / 删除 / 展开能力。上下文文档不再压缩 timeline。
 * - 右侧 agent timeline 协作侧栏：顶部工具条（会话名/保存/清空）+ ConversationTimeline + 底部输入区。
 * - artifact drawer：从右侧抽屉展开，不永久挤压画布。
 *
 * 数据流：
 *   onSend → timeline.pushUser + messages.push(user) → chatSolution(SSE)
 *         → mapSseEvent 把 status/assistant_text/thinking_summary/artifact/... 落进 timeline
 *         → artifact(solution) 经 onSolution 回调更新主画布 solution.value
 *   下一轮 onSend 前 mergePendingAssistant() 把上一轮 assistant_text 合并回 messages
 *   （thinking_summary 不进 messages，与旧实现一致：后端只收 role+content）
 */

// ===== timeline（统一数据模型） =====
const timeline = createTimeline()
// timeline.items 是嵌套在普通对象里的 ref，模板里需用顶层别名才能自动解包
const timelineItems = timeline.items

// ===== 上下文文档 =====
const docs = ref([]) // [{url, markdown, block_count}]
const newUrl = ref('')
const adding = ref(false)
const addError = ref('')

// ===== 对话 / 方案 =====
// messages: 后端上下文 [{role, content}]。user 直接 push；
// assistant 在「下一轮 onSend / 保存」前由 mergePendingAssistant 从 timeline 合并回来。
const messages = ref([])
const inputText = ref('')
const running = ref(false)
const chatError = ref('')
const solution = ref(null) // {title, markdown, summary}

// 已合并进 messages 的最大 timeline item id —— 用于「上一轮 assistant_text 合并回 messages」
const lastMergedTimelineId = ref(0)

// ===== 会话保存 =====
const sessionName = ref('')
const sessionId = ref(null)
const saveStatus = ref('')

// ===== 画布 tab =====
const activeTab = ref('solution') // 'solution' | 'docs'

// ===== artifact drawer =====
const drawerArtifact = ref(null) // AgentArtifact | null
const drawerIsLatest = ref(false)

const totalChars = computed(() =>
  docs.value.reduce((sum, d) => sum + (d.markdown?.length || 0), 0),
)
const drawerOpen = computed(() => drawerArtifact.value !== null)

function fileNameOf(md) {
  if (!md) return '未命名'
  const m = md.match(/^#\s+(.+)$/m)
  if (m) return m[1].trim().slice(0, 40)
  return md.trim().split(/\s+/)[0]?.slice(0, 30) || '未命名'
}

async function onAddDoc() {
  const url = newUrl.value.trim()
  if (!url || adding.value) return
  adding.value = true
  addError.value = ''
  try {
    const res = await loadMany([url])
    const item = res.docs?.[0]
    if (!item) throw new Error('无返回')
    if (item.error) {
      addError.value = item.error
    } else {
      docs.value.push({
        url: item.url,
        markdown: item.markdown || '',
        block_count: item.block_count || 0,
      })
      newUrl.value = ''
    }
  } catch (e) {
    addError.value = e.message
  } finally {
    adding.value = false
  }
}

async function onImportFromSearch(urls) {
  /**从搜索面板批量导入：复用 loadMany，单份失败不影响其它。*/
  if (urls.length === 0 || adding.value) return
  adding.value = true
  addError.value = ''
  try {
    const res = await loadMany(urls)
    let okCount = 0
    for (const item of res.docs || []) {
      if (item.error) continue
      docs.value.push({
        url: item.url,
        markdown: item.markdown || '',
        block_count: item.block_count || 0,
      })
      okCount += 1
    }
    if (okCount === 0) addError.value = '导入失败：未成功加载任何文档'
  } catch (e) {
    addError.value = e.message
  } finally {
    adding.value = false
  }
}

function onRemoveDoc(i) {
  docs.value.splice(i, 1)
}

function onClearDocs() {
  if (docs.value.length === 0) return
  if (!confirm('确定清空所有上下文文档？')) return
  docs.value = []
}

const expandedDoc = ref(-1)
function toggleDoc(i) {
  expandedDoc.value = expandedDoc.value === i ? -1 : i
}

/**
 * 把 timeline 中尚未合并的 assistant_text 合并进 messages（作为上一轮 assistant 回复）。
 * thinking_summary 不进 messages（后端只收 role+content）。
 * 在 onSend / onSaveSession 前调用，保证后端上下文与保存的会话包含 assistant 回复。
 */
function mergePendingAssistant() {
  const pending = timelineItems.value.filter(
    (it) => it.kind === 'assistant_text' && it.id > lastMergedTimelineId.value,
  )
  if (pending.length > 0) {
    const text = pending.map((it) => it.text).join('')
    if (text) messages.value.push({ role: 'assistant', content: text })
  }
  const maxId = timelineItems.value.reduce((m, it) => Math.max(m, it.id), 0)
  lastMergedTimelineId.value = maxId
}

async function onSend() {
  const text = inputText.value.trim()
  if (!text || running.value) return
  if (docs.value.length === 0) {
    chatError.value = '请先添加至少一份上下文文档'
    return
  }
  chatError.value = ''

  // 先把上一轮 assistant_text 合并回 messages，再做本轮 user 推入
  mergePendingAssistant()

  // user 同时进 messages（后端上下文）与 timeline（展示）
  messages.value.push({ role: 'user', content: text })
  timeline.pushUser(text)
  inputText.value = ''

  running.value = true
  try {
    const docsPayload = docs.value.map((d) => ({ url: d.url, markdown: d.markdown }))
    const msgPayload = messages.value.map((m) => ({ role: m.role, content: m.content }))

    await chatSolution(docsPayload, msgPayload, (ev) => {
      mapSseEvent(ev, timeline, {
        onDocumentEdits: () => {},
        onSolution: (payload) => {
          solution.value = {
            title: payload.title,
            markdown: payload.markdown,
            summary: payload.summary,
          }
        },
      })
    })
  } catch (e) {
    chatError.value = e.message
  } finally {
    running.value = false
  }
}

function onExport() {
  if (!solution.value?.markdown) return
  const fname = (solution.value.title || 'solution').replace(/[\\/:*?"<>|]/g, '_')
  exportMd(solution.value.markdown, fname + '.md')
}

// ConversationTimeline / ArtifactDrawer open-artifact(id) → 打开 drawer
function onOpenArtifact(id) {
  const item = timelineItems.value.find((it) => it.id === id)
  if (item && item.kind === 'artifact') {
    drawerArtifact.value = item.artifact
    drawerIsLatest.value = !!item.isLatest
  }
}

function onCloseDrawer() {
  drawerArtifact.value = null
  drawerIsLatest.value = false
}

// drawer SolutionArtifact overwrite-solution → 覆盖当前方案（仅 isLatest 启用）
function onOverwriteFromDrawer() {
  if (!drawerIsLatest.value || !drawerArtifact.value?.payload) return
  const p = drawerArtifact.value.payload
  solution.value = { title: p.title, markdown: p.markdown, summary: p.summary }
}

// action_required 未知 reason 的通用确认（workspace 模式仅 overwrite_solution_confirmation，故此分支不会触发）
function onAction() {}

async function onSaveSession() {
  if (saveStatus.value === 'saving') return
  saveStatus.value = 'saving'
  try {
    mergePendingAssistant() // 保存前补齐最新 assistant 回复
    const name = sessionName.value.trim() || `会话 ${new Date().toLocaleString()}`
    const res = await saveWorkspace({
      sessionId: sessionId.value,
      name,
      docUrls: docs.value.map((d) => d.url),
      messages: messages.value.map((m) => ({ role: m.role, content: m.content })),
      solutionMarkdown: solution.value?.markdown || '',
    })
    sessionId.value = res.session_id
    saveStatus.value = '已保存'
    setTimeout(() => (saveStatus.value = ''), 2000)
  } catch (e) {
    saveStatus.value = '保存失败: ' + e.message
  }
}

function onClearChat() {
  if (timelineItems.value.length === 0 && messages.value.length === 0 && !solution.value) return
  if (!confirm('清空对话和当前方案？上下文文档会保留。')) return
  timeline.reset()
  messages.value = []
  solution.value = null
  chatError.value = ''
  lastMergedTimelineId.value = 0
  drawerArtifact.value = null
  drawerIsLatest.value = false
}

function tabStyle(tab) {
  const active = activeTab.value === tab
  return active
    ? {
        background: 'var(--color-surface-container-lowest)',
        color: 'var(--color-primary)',
      }
    : {
        background: 'transparent',
        color: 'var(--color-on-surface-variant)',
      }
}
</script>

<template>
  <main class="flex-1 flex overflow-hidden">
    <!-- 左侧：主画布（tab 切换当前方案 / 上下文文档） -->
    <section
      class="flex-1 flex flex-col min-w-0"
      :style="{ background: 'var(--color-app-bg)' }"
    >
      <!-- tab 条 -->
      <div
        class="px-4 pt-3 flex items-end gap-1 shrink-0 border-b"
        :style="{
          background: 'var(--color-surface-container)',
          borderColor: 'var(--color-outline-variant)',
        }"
      >
        <button
          @click="activeTab = 'solution'"
          class="px-4 py-2 rounded-t-lg text-[13px] font-medium transition-colors flex items-center gap-2"
          :style="tabStyle('solution')"
        >
          <span class="material-symbols-outlined text-[16px]">article</span>
          当前方案
          <span
            v-if="solution"
            class="px-1.5 py-0.5 rounded-sm text-[10px]"
            :style="{
              background: 'rgba(99, 14, 212, 0.1)',
              color: 'var(--color-primary)',
            }"
            >最新</span
          >
        </button>
        <button
          @click="activeTab = 'docs'"
          class="px-4 py-2 rounded-t-lg text-[13px] font-medium transition-colors flex items-center gap-2"
          :style="tabStyle('docs')"
        >
          <span class="material-symbols-outlined text-[16px]">folder_open</span>
          上下文文档
          <span
            class="px-1.5 py-0.5 rounded-sm text-[10px]"
            :style="{
              background: 'var(--color-surface-container-high)',
              color: 'var(--color-on-surface-variant)',
            }"
            >{{ docs.length }}</span
          >
        </button>
        <div class="ml-auto pb-1">
          <button
            v-if="activeTab === 'solution' && solution"
            @click="onExport"
            class="px-3 py-1.5 rounded text-[13px] font-medium transition-colors flex items-center gap-1"
            :style="{
              background: 'var(--color-secondary)',
              color: 'var(--color-on-secondary)',
            }"
          >
            <span class="material-symbols-outlined text-[16px]">download</span>
            导出 .md
          </button>
        </div>
      </div>

      <!-- 当前方案 tab -->
      <div
        v-if="activeTab === 'solution'"
        class="flex-1 overflow-y-auto"
      >
        <div
          v-if="!solution"
          class="h-full flex flex-col items-center justify-center text-center px-8"
        >
          <span
            class="material-symbols-outlined text-[56px]"
            :style="{ color: 'var(--color-outline-variant)' }"
            >hub</span
          >
          <p
            class="mt-4 text-sm"
            :style="{ color: 'var(--color-on-surface-variant)' }"
          >
            {{
              docs.length === 0
                ? '先在「上下文文档」tab 添加至少一份飞书文档'
                : '在右侧描述目标 / 提需求，Agent 产出的方案会显示在这里'
            }}
          </p>
        </div>
        <div v-else class="p-6 flex flex-col gap-3">
          <div class="flex items-center gap-2 flex-wrap">
            <h2
              class="text-[18px] font-semibold"
              :style="{ color: 'var(--color-on-surface)' }"
            >
              {{ solution.title || '当前方案' }}
            </h2>
            <span
              v-if="solution.summary"
              class="px-2 py-0.5 rounded-sm text-[11px]"
              :style="{
                background: 'rgba(99, 14, 212, 0.1)',
                color: 'var(--color-primary)',
              }"
              >{{ solution.summary }}</span
            >
          </div>
          <div
            class="rounded-lg border p-5 whitespace-pre-wrap text-[13px] leading-relaxed"
            style="font-family: 'JetBrains Mono', ui-monospace, monospace"
            :style="{
              background: 'var(--color-surface)',
              borderColor: 'var(--color-outline-variant)',
              color: 'var(--color-on-surface)',
            }"
          >{{ solution.markdown }}</div>
        </div>
      </div>

      <!-- 上下文文档 tab -->
      <div v-else class="flex-1 flex flex-col min-h-0">
        <!-- URL 输入 -->
        <div
          class="px-4 py-3 shrink-0 flex flex-col gap-2 border-b"
          :style="{ borderColor: 'var(--color-outline-variant)' }"
        >
          <div class="flex items-center justify-between">
            <span
              class="text-[12px]"
              :style="{ color: 'var(--color-on-surface-variant)' }"
            >
              {{ docs.length }} 份 / {{ totalChars }} 字
            </span>
            <button
              @click="onClearDocs"
              :disabled="docs.length === 0"
              class="text-[12px] px-2 py-0.5 rounded transition-colors hover:bg-[var(--color-surface-container)] disabled:opacity-40"
              :style="{ color: 'var(--color-on-surface-variant)' }"
            >
              清空全部
            </button>
          </div>
          <div class="flex gap-2">
            <input
              v-model="newUrl"
              @keydown.enter="onAddDoc"
              type="text"
              placeholder="飞书文档 URL（docx / wiki）"
              class="flex-1 px-2 py-1.5 text-[13px] border rounded focus:outline-none focus:ring-2"
              :style="{
                background: 'var(--color-surface-container-lowest)',
                borderColor: 'var(--color-outline-variant)',
                color: 'var(--color-on-surface)',
              }"
            />
            <button
              @click="onAddDoc"
              :disabled="adding || !newUrl.trim()"
              class="px-3 py-1.5 rounded text-[13px] font-medium transition-colors disabled:opacity-50 flex items-center gap-1"
              :style="{
                background: 'var(--color-primary)',
                color: 'var(--color-on-primary)',
              }"
            >
              <span class="material-symbols-outlined text-[16px]">{{
                adding ? 'sync' : 'add'
              }}</span>
              {{ adding ? '加载中' : '添加' }}
            </button>
          </div>
          <p
            v-if="addError"
            class="text-[12px]"
            :style="{ color: 'var(--color-error)' }"
          >
            {{ addError }}
          </p>
        </div>

        <!-- 搜索导入 -->
        <div
          class="px-4 py-3 border-b flex flex-col min-h-0 shrink-0"
          :style="{
            borderColor: 'var(--color-outline-variant)',
            maxHeight: '38vh',
            minHeight: '180px',
          }"
        >
          <div class="flex items-center gap-1 mb-2 shrink-0">
            <span
              class="material-symbols-outlined text-[15px]"
              :style="{ color: 'var(--color-primary)' }"
              >search</span
            >
            <span
              class="text-[12px] font-medium"
              :style="{ color: 'var(--color-on-surface-variant)' }"
              >搜索导入</span
            >
          </div>
          <div class="flex-1 min-h-0 flex flex-col">
            <DocSearchPanel compact @import="onImportFromSearch" />
          </div>
        </div>

        <!-- 文档列表 -->
        <div class="flex-1 overflow-y-auto p-3 flex flex-col gap-2">
          <div
            v-if="docs.length === 0"
            class="text-center mt-8 text-[13px]"
            :style="{ color: 'var(--color-on-surface-variant)' }"
          >
            先添加至少一份文档作为上下文
          </div>
          <div
            v-for="(d, i) in docs"
            :key="i"
            class="rounded border overflow-hidden"
            :style="{
              background: 'var(--color-surface-container-lowest)',
              borderColor: 'var(--color-outline-variant)',
            }"
          >
            <div class="flex items-center justify-between px-3 py-2 gap-2">
              <button
                class="flex-1 text-left flex items-center gap-2 min-w-0"
                @click="toggleDoc(i)"
              >
                <span
                  class="material-symbols-outlined text-[16px] shrink-0"
                  :style="{ color: 'var(--color-primary)' }"
                  >description</span
                >
                <span
                  class="truncate text-[13px] font-medium"
                  :style="{ color: 'var(--color-on-surface)' }"
                  >{{ fileNameOf(d.markdown) }}</span
                >
                <span
                  class="shrink-0 text-[11px]"
                  :style="{ color: 'var(--color-on-surface-variant)' }"
                  >{{ d.markdown.length }} 字</span
                >
              </button>
              <button
                @click="onRemoveDoc(i)"
                aria-label="删除"
                class="p-1 rounded transition-colors hover:bg-[var(--color-surface-container)]"
                :style="{ color: 'var(--color-on-surface-variant)' }"
              >
                <span class="material-symbols-outlined text-[16px]">close</span>
              </button>
            </div>
            <div
              v-if="expandedDoc === i"
              class="px-3 py-2 text-[12px] whitespace-pre-wrap max-h-48 overflow-y-auto border-t"
              :style="{
                background: 'var(--color-surface-container)',
                borderColor: 'var(--color-outline-variant)',
                color: 'var(--color-on-surface-variant)',
                fontFamily: 'JetBrains Mono, ui-monospace, monospace',
              }"
            >{{ d.markdown.slice(0, 800) }}{{ d.markdown.length > 800 ? '\n...' : '' }}</div>
          </div>
        </div>
      </div>
    </section>

    <!-- 右侧：agent timeline 协作侧栏 -->
    <section
      class="w-[440px] shrink-0 flex flex-col border-l"
      :style="{
        background: 'var(--color-surface)',
        borderColor: 'var(--color-outline-variant)',
      }"
    >
      <!-- 顶部工具条 -->
      <div
        class="px-4 py-3 flex items-center justify-between gap-2 shrink-0 border-b"
        :style="{ borderColor: 'var(--color-outline-variant)' }"
      >
        <input
          v-model="sessionName"
          type="text"
          placeholder="会话名称（可选）"
          class="flex-1 min-w-0 px-2 py-1 text-[13px] border rounded bg-transparent focus:outline-none focus:ring-1"
          :style="{
            borderColor: 'var(--color-outline-variant)',
            color: 'var(--color-on-surface)',
          }"
        />
        <span
          v-if="saveStatus"
          class="text-[12px] shrink-0"
          :style="{ color: 'var(--color-on-surface-variant)' }"
          >{{ saveStatus }}</span
        >
        <button
          @click="onClearChat"
          class="px-2 py-1 rounded text-[12px] transition-colors hover:bg-[var(--color-surface-container)] shrink-0"
          :style="{ color: 'var(--color-on-surface-variant)' }"
        >
          清空
        </button>
        <button
          @click="onSaveSession"
          class="px-3 py-1.5 rounded text-[13px] font-medium transition-colors flex items-center gap-1 border shrink-0"
          :style="{
            background: 'var(--color-surface-container-lowest)',
            borderColor: 'var(--color-outline-variant)',
            color: 'var(--color-on-surface)',
          }"
        >
          <span class="material-symbols-outlined text-[16px]">save</span>
          保存
        </button>
      </div>

      <!-- timeline -->
      <div class="flex-1 overflow-y-auto p-4">
        <div
          v-if="timelineItems.length === 0"
          class="h-full flex flex-col items-center justify-center text-center"
        >
          <span
            class="material-symbols-outlined text-[44px]"
            :style="{ color: 'var(--color-outline-variant)' }"
            >forum</span
          >
          <p
            class="mt-3 text-[13px]"
            :style="{ color: 'var(--color-on-surface-variant)' }"
          >
            描述目标 / 提需求，让 Agent 产出结构化方案
          </p>
        </div>
        <ConversationTimeline
          v-else
          :items="timelineItems"
          :running="running"
          @open-artifact="onOpenArtifact"
          @export-solution="onExport"
          @overwrite-solution="onOverwriteFromDrawer"
          @action="onAction"
        />
      </div>

      <!-- 输入区 -->
      <div
        class="p-3 shrink-0 border-t"
        :style="{ borderColor: 'var(--color-outline-variant)' }"
      >
        <p
          v-if="chatError"
          class="text-[12px] mb-2"
          :style="{ color: 'var(--color-error)' }"
        >
          {{ chatError }}
        </p>
        <div
          class="rounded-lg border focus-within:ring-2"
          :style="{
            background: 'var(--color-surface-container-lowest)',
            borderColor: 'var(--color-outline-variant)',
          }"
        >
          <textarea
            v-model="inputText"
            @keydown.enter.exact.prevent="onSend"
            :disabled="running"
            rows="3"
            placeholder="描述目标、提需求，或要求修改方案的某个部分（Enter 发送，Shift+Enter 换行）"
            class="w-full bg-transparent border-none resize-none focus:outline-none p-3 text-[14px] disabled:opacity-60"
            :style="{ color: 'var(--color-on-surface)' }"
          ></textarea>
          <div
            class="flex items-center justify-between px-3 py-2 rounded-b-lg border-t"
            :style="{
              background: 'var(--color-surface-container)',
              borderColor: 'var(--color-outline-variant)',
            }"
          >
            <span
              class="text-[12px]"
              :style="{ color: 'var(--color-on-surface-variant)' }"
              >{{ docs.length }} 份上下文</span
            >
            <button
              @click="onSend"
              :disabled="running || !inputText.trim() || docs.length === 0"
              class="px-4 py-1.5 rounded text-sm font-medium transition-colors flex items-center gap-2 disabled:opacity-50"
              :style="{
                background: 'var(--color-primary)',
                color: 'var(--color-on-primary)',
              }"
            >
              <span
                class="material-symbols-outlined text-[18px]"
                :class="{ spin: running }"
                >{{ running ? 'sync' : 'send' }}</span
              >
              {{ running ? '生成中...' : '发送' }}
            </button>
          </div>
        </div>
      </div>
    </section>

    <!-- artifact drawer（Teleport 到 body，从右侧抽屉展开） -->
    <ArtifactDrawer
      :open="drawerOpen"
      :artifact="drawerArtifact"
      :is-latest="drawerIsLatest"
      @close="onCloseDrawer"
      @export-solution="onExport"
      @overwrite-solution="onOverwriteFromDrawer"
    />
  </main>
</template>
