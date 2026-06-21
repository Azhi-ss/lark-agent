<script setup>
import { ref, computed, watch, nextTick } from 'vue'

const props = defineProps({
  loaded: { type: Boolean, required: true },
  docMeta: { type: Object, required: true },
  blocks: { type: Array, default: () => [] },
  loadError: { type: String, default: '' },
})
const emit = defineEmits([
  'open-external',
  'accept-suggestion',
  'reject-suggestion',
  'reset-block',
  'edit-block',
])

// P1 仅这些 kind 可编辑（§5.5）
const EDITABLE_KINDS = new Set(['title', 'h1', 'h2', 'h3', 'h4', 'p', 'ul', 'ol', 'pre'])

function isEditable(kind) {
  return EDITABLE_KINDS.has(kind)
}

// contenteditable 用哪种标签渲染
function tagFor(kind) {
  switch (kind) {
    case 'title':
    case 'h1':
      return 'h1'
    case 'h2':
      return 'h2'
    case 'h3':
      return 'h3'
    case 'h4':
      return 'h4'
    case 'pre':
      return 'pre'
    default:
      return 'div' // p / ul / ol
  }
}

// markdown -> 可见文本（剥除该 kind 的语法前缀，用于 contenteditable 初始显示）
function markdownToBlockText(kind, md) {
  if (!md) return ''
  switch (kind) {
    case 'title':
    case 'h1':
      return md.replace(/^#\s+/, '')
    case 'h2':
      return md.replace(/^##\s+/, '')
    case 'h3':
      return md.replace(/^###\s+/, '')
    case 'h4':
      return md.replace(/^####\s+/, '')
    case 'ul':
      return md
        .split('\n')
        .map((l) => l.replace(/^[-*]\s*/, ''))
        .join('\n')
    case 'ol':
      return md
        .split('\n')
        .map((l) => l.replace(/^\d+\.\s*/, ''))
        .join('\n')
    case 'pre':
      return md.replace(/^```[^\n]*\n?/, '').replace(/\n?```$/, '')
    default:
      return md
  }
}

// innerText -> 该 kind 的 markdown（blur 时调用）
function blockTextToMarkdown(kind, text) {
  if (text == null) text = ''
  switch (kind) {
    case 'title':
    case 'h1':
      return `# ${text}`
    case 'h2':
      return `## ${text}`
    case 'h3':
      return `### ${text}`
    case 'h4':
      return `#### ${text}`
    case 'ul':
      return text
        .split('\n')
        .map((l) => (l.trim() ? `- ${l}` : l))
        .join('\n')
    case 'ol':
      return text
        .split('\n')
        .map((l, i) => (l.trim() ? `${i + 1}. ${l}` : l))
        .join('\n')
    case 'pre':
      return '```\n' + text + '\n```'
    default:
      return text
  }
}

// 正在编辑的块下标（防止 watcher 把用户未提交的输入覆盖掉）
const focusedIndex = ref(-1)
// 从右栏「定位到文档」时短暂高亮的块下标
const highlightedIndex = ref(-1)

function onFocus(i) {
  focusedIndex.value = i
}
function onBlur(i, block, e) {
  focusedIndex.value = -1
  emit('edit-block', block.block_id, blockTextToMarkdown(block.kind, e.target.innerText))
}

// 当 block.markdown 被外部改变（接受建议 / 还原 / blur 回写）时，把 contenteditable
// 文本同步成最新值；正在编辑的块跳过。用 markdown 签名做浅 watch，避免每个属性变更都重扫。
const blockMarkdownSignature = computed(() =>
  props.blocks.map((b) => b.markdown).join('\n')
)
function syncAll() {
  for (let i = 0; i < props.blocks.length; i++) {
    const b = props.blocks[i]
    if (!isEditable(b.kind)) continue
    const el = document.getElementById('editable-' + i)
    if (!el) continue
    if (focusedIndex.value === i) continue
    const want = markdownToBlockText(b.kind, b.markdown)
    if (el.innerText !== want) el.innerText = want
  }
}
watch(blockMarkdownSignature, () => nextTick(syncAll), { immediate: true })

// 暴露给 App.vue：从右栏摘要定位到左栏对应 block（滚动 + 高亮）
function scrollToBlock(blockId) {
  const idx = props.blocks.findIndex((b) => b.block_id === blockId)
  if (idx < 0) return
  const el = document.getElementById('doc-block-' + idx)
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' })
  highlightedIndex.value = idx
  window.setTimeout(() => {
    if (highlightedIndex.value === idx) highlightedIndex.value = -1
  }, 1800)
}
defineExpose({ scrollToBlock })

// 只读块占位
function iconFor(kind) {
  return (
    {
      table: 'table_chart',
      figure: 'image',
      img: 'image',
      callout: 'campaign',
      grid: 'grid_on',
      bookmark: 'bookmark',
      cite: 'format_quote',
      hr: 'horizontal_rule',
    }[kind] || 'widgets'
  )
}
function labelFor(kind) {
  return (
    {
      table: '表格',
      figure: '图片/附件',
      img: '图片',
      callout: '提示块',
      grid: '多维表格',
      bookmark: '书签',
      cite: '引用',
      hr: '分隔线',
    }[kind] || kind
  )
}
function truncate(s, n) {
  if (!s) return ''
  return s.length > n ? s.slice(0, n) + '…' : s
}
</script>

<template>
  <section
    class="w-1/2 flex flex-col relative z-10"
    :style="{
      background: 'var(--color-surface-container-lowest)',
      borderRight: '1px solid var(--color-outline-variant)',
      boxShadow: '2px 0 8px rgba(0,0,0,0.02)',
    }"
  >
    <!-- 文档头 -->
    <div
      v-if="loaded"
      class="px-6 py-4 shrink-0 flex items-center justify-between"
      :style="{
        background: 'var(--color-surface)',
        borderBottom: '1px solid var(--color-outline-variant)',
      }"
    >
      <div class="min-w-0">
        <h2
          class="text-[15px] font-medium truncate pr-4"
          :style="{ color: 'var(--color-on-surface)' }"
        >
          飞书周报文档
        </h2>
        <div
          class="flex items-center gap-3 mt-1 text-[13px]"
          :style="{ color: 'var(--color-on-surface-variant)' }"
        >
          <span class="flex items-center gap-1">
            <span class="material-symbols-outlined text-[16px]">fingerprint</span>
            ID: {{ docMeta.document_id || '—' }}
          </span>
          <span class="flex items-center gap-1">
            <span class="material-symbols-outlined text-[16px]">history</span>
            版本: {{ docMeta.revision_id ?? 0 }}
          </span>
          <span class="flex items-center gap-1">
            <span class="material-symbols-outlined text-[16px]">data_object</span>
            块: {{ docMeta.block_count ?? 0 }}
          </span>
        </div>
      </div>
      <button
        @click="$emit('open-external')"
        class="p-1.5 rounded transition-colors hover:bg-[var(--color-surface-container)]"
        :style="{ color: 'var(--color-outline)' }"
        title="在飞书中打开"
      >
        <span class="material-symbols-outlined">open_in_new</span>
      </button>
    </div>

    <!-- 加载错误 -->
    <div
      v-if="loadError"
      class="px-6 py-2 text-sm shrink-0"
      :style="{
        background: 'var(--color-danger-surface)',
        color: 'var(--color-danger-text)',
        borderBottom: '1px solid var(--color-outline-variant)',
      }"
    >
      {{ loadError }}
    </div>

    <!-- 文档正文：逐 block 渲染 -->
    <div class="flex-1 overflow-y-auto px-10 py-8 relative">
      <div v-if="!loaded" class="text-center mt-20">
        <span
          class="material-symbols-outlined text-[48px]"
          :style="{ color: 'var(--color-outline-variant)' }"
        >
          description
        </span>
        <p
          class="mt-3 text-sm"
          :style="{ color: 'var(--color-on-surface-variant)' }"
        >
          输入飞书周报 URL 并点击「加载文档」
        </p>
      </div>

      <div
        v-else-if="blocks.length === 0"
        class="text-center mt-20"
      >
        <span
          class="material-symbols-outlined text-[40px]"
          :style="{ color: 'var(--color-outline-variant)' }"
        >
          drafts
        </span>
        <p
          class="mt-2 text-sm"
          :style="{ color: 'var(--color-on-surface-variant)' }"
        >
          文档无可用块（后端未返回 blocks）
        </p>
      </div>

      <div v-else class="max-w-3xl mx-auto flex flex-col gap-3 markdown-body">
        <div
          v-for="(block, i) in blocks"
          :key="i"
          :id="'doc-block-' + i"
          class="doc-block"
          :class="{ 'doc-block--highlight': highlightedIndex === i }"
        >
          <!-- 可编辑块 -->
          <div v-if="isEditable(block.kind)" class="editable-wrap">
            <div class="editable-row">
              <component
                :is="tagFor(block.kind)"
                contenteditable="true"
                spellcheck="false"
                :id="'editable-' + i"
                :data-kind="block.kind"
                class="editable-content"
                :class="['kind-' + block.kind, { 'is-edited': block.edited }]"
                @focus="onFocus(i)"
                @blur="onBlur(i, block, $event)"
              ></component>
              <button
                v-if="block.edited"
                class="reset-btn"
                title="还原该块为加载时的内容"
                @click="$emit('reset-block', block.block_id)"
              >
                <span class="material-symbols-outlined text-[15px]">restart_alt</span>还原
              </button>
            </div>
          </div>

          <!-- 只读：hr 渲染为分隔线 -->
          <div v-else-if="block.kind === 'hr'" class="readonly-hr">
            <hr />
          </div>

          <!-- 只读占位：table/figure/img/callout/grid/bookmark/cite -->
          <div v-else class="readonly-block">
            <span class="material-symbols-outlined readonly-icon">{{ iconFor(block.kind) }}</span>
            <span class="readonly-label">{{ labelFor(block.kind) }}</span>
            <span class="readonly-text">{{ truncate(block.text, 60) }}</span>
          </div>

          <!-- 待处理建议预览（接受/拒绝） -->
          <div
            v-if="block.suggestion && block.suggestion.state === 'pending'"
            class="suggestion-card"
          >
            <div class="suggestion-head">
              <span class="material-symbols-outlined suggestion-icon">edit_note</span>
              <span class="suggestion-reason">{{ block.suggestion.reason || '修改建议' }}</span>
            </div>
            <pre class="suggestion-content">{{ block.suggestion.content }}</pre>
            <div class="suggestion-actions">
              <button
                class="btn-reject"
                @click="$emit('reject-suggestion', block.block_id)"
              >
                拒绝
              </button>
              <button
                class="btn-accept"
                @click="$emit('accept-suggestion', block.block_id)"
              >
                接受
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.doc-block {
  position: relative;
  border-radius: 6px;
  padding: 2px 4px;
  transition: box-shadow 0.2s ease;
}
.doc-block--highlight {
  box-shadow: 0 0 0 2px var(--color-primary);
}

.editable-wrap {
  position: relative;
}
.editable-row {
  display: flex;
  align-items: flex-start;
  gap: 6px;
}
.editable-content {
  flex: 1;
  min-width: 0;
  outline: none;
  padding: 2px 6px;
  margin: 0 -6px;
  border-radius: 4px;
  border-left: 3px solid transparent;
  transition: background 0.15s ease, border-color 0.15s ease;
  line-height: 1.6;
  word-break: break-word;
  white-space: pre-wrap;
}
.editable-content:hover {
  background: var(--color-surface-container);
}
.editable-content:focus {
  background: var(--color-surface-container-low);
  border-left-color: var(--color-primary);
}
.editable-content.is-edited {
  border-left-color: var(--color-secondary);
  background: var(--color-success-surface);
}

/* 各 kind 字号（沿用 markdown-body 视觉） */
.kind-title,
.kind-h1 {
  font-size: 1.6em;
  font-weight: 700;
  margin: 0.4em 0 0.2em;
}
.kind-h2 {
  font-size: 1.35em;
  font-weight: 600;
  margin: 0.4em 0 0.2em;
}
.kind-h3 {
  font-size: 1.15em;
  font-weight: 600;
  margin: 0.3em 0 0.2em;
}
.kind-h4 {
  font-size: 1em;
  font-weight: 600;
  margin: 0.3em 0 0.2em;
}
.kind-p {
  margin: 0.2em 0;
}
.kind-ul,
.kind-ol {
  padding-left: 14px;
  border-left: 2px solid var(--color-outline-variant);
}
.kind-pre {
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 13px;
  background: var(--color-surface-container);
  padding: 10px 12px;
  border-radius: 6px;
  white-space: pre-wrap;
  margin: 0.2em 0;
}

/* 还原按钮 */
.reset-btn {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  flex-shrink: 0;
  margin-top: 4px;
  padding: 2px 8px;
  font-size: 12px;
  border-radius: 999px;
  border: 1px solid var(--color-outline-variant);
  background: var(--color-surface);
  color: var(--color-on-surface-variant);
  transition: background 0.15s ease;
}
.reset-btn:hover {
  background: var(--color-surface-container-high);
}

/* 只读占位 */
.readonly-hr {
  margin: 0.4em 0;
}
.readonly-hr hr {
  border: none;
  border-top: 1px solid var(--color-outline-variant);
  margin: 0;
}
.readonly-block {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 6px;
  background: var(--color-surface-container);
  color: var(--color-on-surface-variant);
  font-size: 13px;
}
.readonly-icon {
  font-size: 18px;
  color: var(--color-outline);
}
.readonly-label {
  font-weight: 600;
  color: var(--color-on-surface-variant);
}
.readonly-text {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  opacity: 0.8;
}

/* 建议预览卡片 */
.suggestion-card {
  margin: 6px 0 6px 18px;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid rgba(99, 14, 212, 0.3);
  box-shadow: 0 4px 12px rgba(99, 14, 212, 0.06);
  background: var(--color-surface);
}
.suggestion-head {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: rgba(124, 58, 237, 0.05);
  border-bottom: 1px solid var(--color-outline-variant);
}
.suggestion-icon {
  font-size: 18px;
  color: var(--color-primary);
}
.suggestion-reason {
  font-size: 13px;
  font-weight: 600;
  color: var(--color-primary);
}
.suggestion-content {
  margin: 0;
  padding: 10px 12px;
  font-family: 'JetBrains Mono', ui-monospace, monospace;
  font-size: 13px;
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--color-on-surface);
}
.suggestion-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 8px 12px;
  background: var(--color-surface-container-lowest);
  border-top: 1px solid var(--color-outline-variant);
}
.btn-reject,
.btn-accept {
  padding: 4px 12px;
  border-radius: 6px;
  font-size: 13px;
  transition: background 0.15s ease;
}
.btn-reject {
  color: var(--color-on-surface-variant);
}
.btn-reject:hover {
  background: var(--color-surface-variant);
}
.btn-accept {
  background: var(--color-primary);
  color: var(--color-on-primary);
}
.btn-accept:hover {
  filter: brightness(1.05);
}
</style>
