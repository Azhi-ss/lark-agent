<script setup>
import { ref, computed } from 'vue'
import { loadDoc, chatAgent, applyEdits } from './api.js'
import TopBar from './components/TopBar.vue'
import DocPane from './components/DocPane.vue'
import AgentPane from './components/AgentPane.vue'
import AppFooter from './components/AppFooter.vue'
import WorkspaceView from './components/WorkspaceView.vue'
import SettingsModal from './components/SettingsModal.vue'

const activeMode = ref('editor') // 'editor' | 'workspace'
const settingsOpen = ref(false)

const docUrl = ref('https://dptechnology.feishu.cn/wiki/OWAIwHYLJiyEHjkJvRAcEmKnn7y')
const markdown = ref('')
const docMeta = ref({ document_id: '', revision_id: 0, block_count: 0 })
const loading = ref(false)
const loadError = ref('')

const instruction = ref('提炼本周（最近一篇）核心要点，在文末追加"## 本周要点"摘要段落。')
const agentText = ref('')
const agentThinking = ref('')
const replacements = ref([])
const running = ref(false)
const applyStatus = ref('')
const applying = ref(false)

const loaded = computed(() => markdown.value.length > 0)

async function onLoad() {
  if (loading.value) return
  loading.value = true
  loadError.value = ''
  markdown.value = ''
  replacements.value = []
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
  } catch (e) {
    loadError.value = e.message
  } finally {
    loading.value = false
  }
}

async function onChat() {
  if (!loaded.value || running.value) return
  running.value = true
  agentText.value = ''
  agentThinking.value = ''
  replacements.value = []
  applyStatus.value = ''
  try {
    await chatAgent(markdown.value, instruction.value, (ev) => {
      if (ev.type === 'thinking') {
        agentThinking.value += ev.data.text
      } else if (ev.type === 'text') {
        agentText.value += ev.data.text
      } else if (ev.type === 'done') {
        replacements.value = ev.data.replacements || []
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

async function onApply() {
  if (replacements.value.length === 0 || applying.value) return
  applying.value = true
  applyStatus.value = '写回中...'
  try {
    const res = await applyEdits(docUrl.value, replacements.value)
    applyStatus.value = res.ok
      ? `已写回飞书（${res.count} 处）`
      : `部分失败：${res.results.filter((r) => !r.ok).length} 处`
    if (res.ok) replacements.value = []
  } catch (e) {
    applyStatus.value = '写回失败: ' + e.message
  } finally {
    applying.value = false
  }
}

function onQuickAction(text) {
  instruction.value = text
}

function onReject(i) {
  replacements.value = replacements.value.filter((_, idx) => idx !== i)
}

function onAccept(_i) {
  // 单条接受暂不处理（写回是批量动作）；保留卡片以便最终统一写回
}

function onOpenExternal() {
  if (docUrl.value) {
    window.open(docUrl.value, '_blank', 'noopener')
  }
}

// 简易 markdown 渲染（保留原实现）
function renderMd(src) {
  if (!src) return ''
  const esc = (s) =>
    s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  const lines = esc(src).split('\n')
  let html = ''
  let inCode = false
  let inUl = false
  let inOl = false
  const inline = (s) =>
    s
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  for (let line of lines) {
    if (line.startsWith('```')) {
      if (inCode) {
        html += '</code></pre>'
        inCode = false
      } else {
        if (inUl) { html += '</ul>'; inUl = false }
        if (inOl) { html += '</ol>'; inOl = false }
        html += '<pre><code>'
        inCode = true
      }
      continue
    }
    if (inCode) {
      html += line + '\n'
      continue
    }
    if (/^###\s/.test(line)) {
      if (inUl) { html += '</ul>'; inUl = false }
      if (inOl) { html += '</ol>'; inOl = false }
      html += `<h3>${inline(line.replace(/^###\s/, ''))}</h3>`
    } else if (/^##\s/.test(line)) {
      if (inUl) { html += '</ul>'; inUl = false }
      if (inOl) { html += '</ol>'; inOl = false }
      html += `<h2>${inline(line.replace(/^##\s/, ''))}</h2>`
    } else if (/^#\s/.test(line)) {
      if (inUl) { html += '</ul>'; inUl = false }
      if (inOl) { html += '</ol>'; inOl = false }
      html += `<h1>${inline(line.replace(/^#\s/, ''))}</h1>`
    } else if (/^[-*]\s/.test(line)) {
      if (inOl) { html += '</ol>'; inOl = false }
      if (!inUl) { html += '<ul>'; inUl = true }
      html += `<li>${inline(line.replace(/^[-*]\s/, ''))}</li>`
    } else if (/^\d+\.\s/.test(line)) {
      if (inUl) { html += '</ul>'; inUl = false }
      if (!inOl) { html += '<ol>'; inOl = true }
      html += `<li>${inline(line.replace(/^\d+\.\s/, ''))}</li>`
    } else if (line.trim() === '') {
      if (inUl) { html += '</ul>'; inUl = false }
      if (inOl) { html += '</ol>'; inOl = false }
    } else {
      if (inUl) { html += '</ul>'; inUl = false }
      if (inOl) { html += '</ol>'; inOl = false }
      html += `<p>${inline(line)}</p>`
    }
  }
  if (inUl) html += '</ul>'
  if (inOl) html += '</ol>'
  if (inCode) html += '</code></pre>'
  return html
}

const markdownHtml = computed(() => renderMd(markdown.value))
</script>

<template>
  <div class="h-screen flex flex-col overflow-hidden">
    <TopBar v-model="docUrl" :loading="loading" @load="onLoad" @open-settings="settingsOpen = true">
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
          :loaded="loaded"
          :doc-meta="docMeta"
          :markdown-html="markdownHtml"
          :load-error="loadError"
          @open-external="onOpenExternal"
        />
        <AgentPane
          :loaded="loaded"
          :running="running"
          :instruction="instruction"
          :agent-text="agentText"
          :agent-thinking="agentThinking"
          :replacements="replacements"
          @update:instruction="instruction = $event"
          @chat="onChat"
          @quick-action="onQuickAction"
          @reject="onReject"
          @accept="onAccept"
        />
      </main>
      <WorkspaceView v-else key="workspace" />
    </Transition>

    <AppFooter
      v-if="activeMode === 'editor'"
      :replacements-count="replacements.length"
      :apply-status="applyStatus"
      :applying="applying"
      @apply="onApply"
    />

    <SettingsModal
      :open="settingsOpen"
      @close="settingsOpen = false"
      @saved="(cfg) => (settingsOpen = false)"
    />
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
