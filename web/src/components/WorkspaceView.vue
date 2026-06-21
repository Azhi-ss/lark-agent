<script setup>
import { ref, computed } from 'vue'
import {
  loadMany,
  chatSolution,
  exportMd,
  saveWorkspace,
} from '../api.js'
import DocSearchPanel from './DocSearchPanel.vue'

/**
 * 方案构建模式：
 * - 左栏：上下文文档列表（可加载多份飞书文档）
 * - 右栏：与 agent 对话；agent 通过 produce_solution 工具产出/更新方案 markdown
 */

const docs = ref([]) // [{url, markdown, error}]
const newUrl = ref('')
const adding = ref(false)
const addError = ref('')

const messages = ref([]) // [{role, content, thinking?}]
const inputText = ref('')
const running = ref(false)
const chatError = ref('')

// 当前最新一版方案
const solution = ref(null) // {title, markdown, summary}

// 流式中正在累积的 assistant 消息（占位）
const streamingMsg = ref(null)

const sessionName = ref('')
const sessionId = ref(null)
const saveStatus = ref('')

const totalChars = computed(() =>
  docs.value.reduce((sum, d) => sum + (d.markdown?.length || 0), 0),
)

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

async function onSend() {
  const text = inputText.value.trim()
  if (!text || running.value) return
  if (docs.value.length === 0) {
    chatError.value = '请先添加至少一份上下文文档'
    return
  }
  chatError.value = ''
  // 追加 user 消息
  messages.value.push({ role: 'user', content: text })
  inputText.value = ''

  // 占位 assistant 消息
  const placeholder = { role: 'assistant', content: '', thinking: '' }
  streamingMsg.value = placeholder
  messages.value.push(placeholder)

  running.value = true
  try {
    const docsPayload = docs.value.map((d) => ({ url: d.url, markdown: d.markdown }))
    // 只传 role+content，不传 thinking
    const msgPayload = messages.value
      .filter((m) => m !== placeholder)
      .map((m) => ({ role: m.role, content: m.content }))

    await chatSolution(docsPayload, msgPayload, (ev) => {
      if (ev.type === 'thinking') {
        placeholder.thinking = (placeholder.thinking || '') + ev.data.text
      } else if (ev.type === 'text') {
        placeholder.content = (placeholder.content || '') + ev.data.text
      } else if (ev.type === 'done') {
        if (ev.data.solution) {
          solution.value = ev.data.solution
        }
      } else if (ev.type === 'error') {
        chatError.value = ev.data.message
      }
    })
  } catch (e) {
    chatError.value = e.message
  } finally {
    running.value = false
    streamingMsg.value = null
  }
}

function onExport() {
  if (!solution.value?.markdown) return
  const fname = (solution.value.title || 'solution').replace(/[\\/:*?"<>|]/g, '_')
  exportMd(solution.value.markdown, fname + '.md')
}

async function onSaveSession() {
  if (saveStatus.value === 'saving') return
  saveStatus.value = 'saving'
  try {
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
  if (messages.value.length === 0 && !solution.value) return
  if (!confirm('清空对话和当前方案？上下文文档会保留。')) return
  messages.value = []
  solution.value = null
  chatError.value = ''
}
</script>

<template>
  <main class="flex-1 flex overflow-hidden">
    <!-- 左栏：上下文文档列表 -->
    <section
      class="w-[360px] flex flex-col shrink-0 border-r"
      :style="{
        background: 'var(--color-surface)',
        borderColor: 'var(--color-outline-variant)',
      }"
    >
      <!-- 标题 + 清空 -->
      <div
        class="px-4 py-3 flex items-center justify-between shrink-0 border-b"
        :style="{ borderColor: 'var(--color-outline-variant)' }"
      >
        <div class="flex items-center gap-2">
          <span
            class="material-symbols-outlined text-[20px]"
            :style="{ color: 'var(--color-primary)' }"
            >folder_open</span
          >
          <h3
            class="font-semibold text-[15px]"
            :style="{ color: 'var(--color-on-surface)' }"
          >
            上下文文档
          </h3>
          <span
            class="text-[12px]"
            :style="{ color: 'var(--color-on-surface-variant)' }"
          >
            {{ docs.length }} 份 / {{ totalChars }} 字
          </span>
        </div>
        <button
          @click="onClearDocs"
          :disabled="docs.length === 0"
          class="text-[12px] px-2 py-0.5 rounded transition-colors hover:bg-[var(--color-surface-container)] disabled:opacity-40"
          :style="{ color: 'var(--color-on-surface-variant)' }"
        >
          清空全部
        </button>
      </div>

      <!-- URL 输入 -->
      <div class="px-4 py-3 shrink-0 flex flex-col gap-2 border-b"
        :style="{ borderColor: 'var(--color-outline-variant)' }">
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
      <div class="px-4 py-3 shrink-0 border-b" :style="{ borderColor: 'var(--color-outline-variant)' }">
        <div class="flex items-center gap-1 mb-2">
          <span class="material-symbols-outlined text-[15px]" :style="{ color: 'var(--color-primary)' }">search</span>
          <span class="text-[12px] font-medium" :style="{ color: 'var(--color-on-surface-variant)' }">搜索导入</span>
        </div>
        <DocSearchPanel compact @import="onImportFromSearch" />
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
    </section>

    <!-- 右栏：对话 -->
    <section
      class="flex-1 flex flex-col"
      :style="{ background: 'var(--color-app-bg)' }"
    >
      <!-- 顶部工具条 -->
      <div
        class="px-6 py-3 flex items-center justify-between gap-3 shrink-0 border-b"
        :style="{
          background: 'var(--color-surface)',
          borderColor: 'var(--color-outline-variant)',
        }"
      >
        <div class="flex items-center gap-2 min-w-0 flex-1">
          <input
            v-model="sessionName"
            type="text"
            placeholder="会话名称（可选）"
            class="flex-1 max-w-md px-2 py-1 text-[13px] border rounded bg-transparent focus:outline-none focus:ring-1"
            :style="{
              borderColor: 'var(--color-outline-variant)',
              color: 'var(--color-on-surface)',
            }"
          />
          <span
            v-if="saveStatus"
            class="text-[12px]"
            :style="{ color: 'var(--color-on-surface-variant)' }"
            >{{ saveStatus }}</span
          >
        </div>
        <div class="flex items-center gap-2">
          <button
            @click="onClearChat"
            class="px-2 py-1 rounded text-[12px] transition-colors hover:bg-[var(--color-surface-container)]"
            :style="{ color: 'var(--color-on-surface-variant)' }"
          >
            清空对话
          </button>
          <button
            @click="onSaveSession"
            class="px-3 py-1.5 rounded text-[13px] font-medium transition-colors flex items-center gap-1 border"
            :style="{
              background: 'var(--color-surface-container-lowest)',
              borderColor: 'var(--color-outline-variant)',
              color: 'var(--color-on-surface)',
            }"
          >
            <span class="material-symbols-outlined text-[16px]">save</span>
            保存会话
          </button>
        </div>
      </div>

      <!-- 消息区 -->
      <div class="flex-1 overflow-y-auto p-6 flex flex-col gap-3">
        <div
          v-if="messages.length === 0"
          class="text-center mt-16"
        >
          <span
            class="material-symbols-outlined text-[48px]"
            :style="{ color: 'var(--color-outline-variant)' }"
            >hub</span
          >
          <p
            class="mt-3 text-sm"
            :style="{ color: 'var(--color-on-surface-variant)' }"
          >
            {{
              docs.length === 0
                ? '请先在左侧添加上下文文档'
                : '描述目标 / 提需求，让 Agent 产出结构化方案'
            }}
          </p>
        </div>

        <div
          v-for="(m, i) in messages"
          :key="i"
          class="flex gap-3 fade-in"
          :class="m.role === 'user' ? 'flex-row-reverse' : ''"
        >
          <div
            class="w-8 h-8 rounded-full flex items-center justify-center shrink-0"
            :style="{
              background:
                m.role === 'user'
                  ? 'var(--color-surface-container-high)'
                  : 'var(--color-primary-container)',
              color:
                m.role === 'user'
                  ? 'var(--color-on-surface)'
                  : 'var(--color-on-primary-container)',
            }"
          >
            <span class="material-symbols-outlined text-[20px]">{{
              m.role === 'user' ? 'person' : 'smart_toy'
            }}</span>
          </div>
          <div class="flex flex-col gap-2 max-w-[80%]">
            <!-- thinking 折叠 -->
            <details
              v-if="m.role === 'assistant' && m.thinking"
              class="rounded border text-[12px]"
              :style="{
                background: 'var(--color-thinking-gray)',
                borderColor: 'var(--color-outline-variant)',
                color: 'var(--color-on-surface-variant)',
                fontFamily: 'JetBrains Mono, ui-monospace, monospace',
              }"
            >
              <summary class="cursor-pointer px-3 py-1.5">思考过程</summary>
              <div class="px-3 py-2 whitespace-pre-wrap">{{ m.thinking }}</div>
            </details>
            <div
              v-if="m.content"
              class="rounded-lg p-3 shadow-sm border whitespace-pre-wrap text-[14px]"
              :style="{
                background:
                  m.role === 'user'
                    ? 'var(--color-primary-container)'
                    : 'var(--color-surface)',
                borderColor: 'var(--color-outline-variant)',
                color:
                  m.role === 'user'
                    ? 'var(--color-on-primary-container)'
                    : 'var(--color-on-surface)',
              }"
            >{{ m.content }}</div>
          </div>
        </div>

        <!-- 当前方案卡片 -->
        <div
          v-if="solution"
          class="rounded-lg border fade-in mt-2"
          :style="{
            background: 'var(--color-surface)',
            borderColor: 'rgba(99, 14, 212, 0.3)',
            boxShadow: '0 4px 12px rgba(99, 14, 212, 0.06)',
          }"
        >
          <div
            class="px-4 py-3 flex items-center justify-between border-b"
            :style="{
              background: 'rgba(124, 58, 237, 0.05)',
              borderColor: 'var(--color-outline-variant)',
            }"
          >
            <div class="flex items-center gap-2 min-w-0">
              <span
                class="material-symbols-outlined text-[18px] shrink-0"
                :style="{ color: 'var(--color-primary)' }"
                >article</span
              >
              <h4
                class="font-semibold text-[15px] truncate"
                :style="{ color: 'var(--color-on-surface)' }"
              >
                {{ solution.title || '当前方案' }}
              </h4>
              <span
                v-if="solution.summary"
                class="px-2 py-0.5 rounded-sm text-[11px] shrink-0"
                :style="{
                  background: 'rgba(99, 14, 212, 0.1)',
                  color: 'var(--color-primary)',
                }"
                >{{ solution.summary }}</span
              >
            </div>
            <button
              @click="onExport"
              class="px-3 py-1.5 rounded text-[13px] font-medium transition-colors flex items-center gap-1"
              :style="{
                background: 'var(--color-secondary)',
                color: 'var(--color-on-secondary)',
              }"
            >
              <span class="material-symbols-outlined text-[16px]"
                >download</span
              >
              导出方案 .md
            </button>
          </div>
          <div
            class="p-4 max-h-[420px] overflow-y-auto whitespace-pre-wrap text-[13px]"
            style="font-family: 'JetBrains Mono', ui-monospace, monospace"
            :style="{ color: 'var(--color-on-surface)' }"
          >{{ solution.markdown }}</div>
        </div>

        <p
          v-if="chatError"
          class="text-[13px] mt-2"
          :style="{ color: 'var(--color-error)' }"
        >
          {{ chatError }}
        </p>
      </div>

      <!-- 输入区 -->
      <div
        class="p-4 shrink-0 border-t"
        :style="{
          background: 'var(--color-surface)',
          borderColor: 'var(--color-outline-variant)',
        }"
      >
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
              >{{ docs.length }} 份上下文 · {{ messages.length }} 条对话</span
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
  </main>
</template>
