<script setup>
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import { iconFor, isEditable, labelFor, matchMarkdownShortcut, tagFor, truncate } from './docPaneHelpers.js'

const props = defineProps({
  loaded: { type: Boolean, required: true },
  docMeta: { type: Object, required: true },
  blocks: { type: Array, default: () => [] },
  loadError: { type: String, default: '' },
  recentDocs: { type: Array, default: () => [] },
})
const emit = defineEmits([
  'open-external',
  'accept-suggestion',
  'reject-suggestion',
  'reset-block',
  'edit-block',
  'load-recent',
  'remove-recent',
  'open-search',
  // 新增（单一 contenteditable 架构）
  'split-block',
  'merge-blocks',
  'change-block-kind',
  'blocks-changed',
])

const editorRef = ref(null) // 单一 contenteditable 容器
const editorShellRef = ref(null) // 定位祖先（浮动还原按钮参考系）

// 当前聚焦块下标（-1 表示无聚焦）。用于：
//  - 跳过 watcher 对聚焦块的 text 同步（避免覆盖光标位置）
//  - 显示浮动还原按钮
const focusedIndex = ref(-1)
// 从右栏「定位到文档」时短暂高亮的块下标
const highlightedIndex = ref(-1)
// 浮动还原按钮位置（top:-9999 表示隐藏）
const resetBtnPos = ref({ top: -9999, left: 0 })

const focusedBlock = computed(() =>
  focusedIndex.value >= 0 ? props.blocks[focusedIndex.value] : null
)

// ─── 工具：定位光标所在 block 元素 ───
function getCurrentBlockEl() {
  const sel = window.getSelection()
  if (!sel || !sel.rangeCount) return null
  let node = sel.anchorNode
  const editor = editorRef.value
  while (node && node !== editor) {
    if (node.dataset && node.dataset.blockId !== undefined) return node
    node = node.parentNode
  }
  return null
}

// 判断元素是否为可编辑块（有 data-block-id 且未标记 contenteditable=false）
function isEditableBlockEl(el) {
  return !!el && el.hasAttribute('data-block-id') && el.getAttribute('contenteditable') !== 'false'
}

function getPreviousEditableBlockEl(el) {
  let prev = el.previousElementSibling
  while (prev) {
    if (isEditableBlockEl(prev)) return prev
    prev = prev.previousElementSibling
  }
  return null
}
function getNextEditableBlockEl(el) {
  let next = el.nextElementSibling
  while (next) {
    if (isEditableBlockEl(next)) return next
    next = next.nextElementSibling
  }
  return null
}

// 光标在 block 内的字符偏移
function getCaretOffsetWithin(blockEl, range) {
  const preRange = range.cloneRange()
  preRange.selectNodeContents(blockEl)
  preRange.setEnd(range.endContainer, range.endOffset)
  return preRange.toString().length
}
// 光标是否在 block 起始（前面无文本）
function isCaretAtBlockStart(blockEl, range) {
  if (!range.collapsed) return false
  const preRange = range.cloneRange()
  preRange.selectNodeContents(blockEl)
  preRange.setEnd(range.endContainer, range.endOffset)
  return preRange.toString() === ''
}
// 光标是否在 block 第一行（块首→上箭头应跳上一块）
function isCaretOnFirstLine(blockEl, range) {
  const testRange = document.createRange()
  testRange.selectNodeContents(blockEl)
  testRange.setEnd(range.endContainer, range.endOffset)
  return testRange.getClientRects().length <= 1
}
// 光标是否在 block 最后一行（块末→下箭头应跳下一块）
function isCaretOnLastLine(blockEl, range) {
  const testRange = document.createRange()
  testRange.selectNodeContents(blockEl)
  testRange.setStart(range.endContainer, range.endOffset)
  return testRange.getClientRects().length <= 1
}

function placeCaretAtEnd(el) {
  const range = document.createRange()
  range.selectNodeContents(el)
  range.collapse(false)
  const sel = window.getSelection()
  sel.removeAllRanges()
  sel.addRange(range)
}
function placeCaretAtStart(el) {
  const range = document.createRange()
  range.selectNodeContents(el)
  range.collapse(true)
  const sel = window.getSelection()
  sel.removeAllRanges()
  sel.addRange(range)
}

// ─── keydown：Enter / Backspace / ArrowUp / ArrowDown ───
function onKeydown(e) {
  const blockEl = getCurrentBlockEl()
  if (!blockEl || !isEditableBlockEl(blockEl)) return

  const sel = window.getSelection()
  if (!sel || !sel.rangeCount) return
  const range = sel.getRangeAt(0)

  // Enter：分裂 block（pre 例外，插入换行）
  if (e.key === 'Enter' && !e.shiftKey) {
    if (blockEl.dataset.kind === 'pre') {
      e.preventDefault()
      document.execCommand('insertText', false, '\n')
      scheduleSync()
      return
    }
    e.preventDefault()
    const cursorPos = getCaretOffsetWithin(blockEl, range)
    const fullText = blockEl.innerText
    const textBefore = fullText.slice(0, cursorPos)
    const textAfter = fullText.slice(cursorPos)
    emit('split-block', blockEl.dataset.blockId, cursorPos, textBefore, textAfter)
    return
  }

  // Backspace：块首且有上一可编辑块 → 合并
  if (e.key === 'Backspace') {
    if (!isCaretAtBlockStart(blockEl, range)) return
    const prev = getPreviousEditableBlockEl(blockEl)
    if (!prev) return
    e.preventDefault()
    emit('merge-blocks', blockEl.dataset.blockId, prev.dataset.blockId)
    return
  }

  // ArrowUp / ArrowDown：跨 block 移动
  if (e.key === 'ArrowUp' && isCaretOnFirstLine(blockEl, range)) {
    const prev = getPreviousEditableBlockEl(blockEl)
    if (prev) {
      e.preventDefault()
      placeCaretAtEnd(prev)
      nextTick(updateResetBtnPos)
    }
    return
  }
  if (e.key === 'ArrowDown' && isCaretOnLastLine(blockEl, range)) {
    const next = getNextEditableBlockEl(blockEl)
    if (next) {
      e.preventDefault()
      placeCaretAtStart(next)
      nextTick(updateResetBtnPos)
    }
    return
  }
}

// ─── input：Markdown 快捷输入 + debounce 同步 ───
function onInput() {
  const blockEl = getCurrentBlockEl()
  if (!blockEl || !isEditableBlockEl(blockEl)) {
    scheduleSync()
    return
  }
  const text = blockEl.innerText
  const shortcut = matchMarkdownShortcut(text)
  if (shortcut && blockEl.dataset.kind !== shortcut.kind) {
    emit('change-block-kind', blockEl.dataset.blockId, shortcut.kind, shortcut.cleaned)
    // 乐观更新本地文本（移除前缀），避免 App.vue 未接入时残留 "# "
    blockEl.innerText = shortcut.cleaned
    placeCaretAtStart(blockEl)
    return
  }
  scheduleSync()
  nextTick(updateResetBtnPos)
}

// ─── debounce 300ms 收集变更，比对 props 后 emit ───
let syncTimer = null
function scheduleSync() {
  if (syncTimer) clearTimeout(syncTimer)
  syncTimer = setTimeout(() => {
    syncTimer = null
    flushChanges()
  }, 300)
}

function flushChanges() {
  const editor = editorRef.value
  if (!editor) return
  const blockEls = editor.querySelectorAll('[data-block-id]')
  const changed = []
  for (let i = 0; i < props.blocks.length && i < blockEls.length; i++) {
    const el = blockEls[i]
    if (!isEditableBlockEl(el)) continue
    const b = props.blocks[i]
    const raw = el.innerText
    // contenteditable 清空后 innerText 常为 "\n"（残留 <br>），归一化为空串 → 走 block_delete
    const text = raw === '\n' || raw.trim() === '' ? '' : raw
    if (text !== b.text) {
      changed.push({ block_id: b.block_id, text, kind: el.dataset.kind })
    }
  }
  if (changed.length > 0) emit('blocks-changed', changed)
}

// ─── 文本同步 watcher：外部变更（接受建议 / 还原 / 写回刷新）同步到 DOM ───
// 签名含 kind + text + block_id，覆盖文本变化、kind 变化、结构变化。
// 只在非聚焦块上同步，避免覆盖光标位置；聚焦块若因 kind 变化被 Vue 重建为空壳则补写文本。
const blockSignature = computed(() =>
  props.blocks.map((b) => JSON.stringify([b.kind, b.text, b.block_id || ''])).join('\n')
)
function syncBlockTexts() {
  const editor = editorRef.value
  if (!editor) return
  const blockEls = editor.querySelectorAll('[data-block-id]')
  const focused = getCurrentBlockEl()
  for (let i = 0; i < props.blocks.length && i < blockEls.length; i++) {
    const el = blockEls[i]
    const b = props.blocks[i]
    if (!isEditableBlockEl(el)) continue
    if (el === focused) {
      // 聚焦块：仅在 Vue 因 kind 变化重建出空壳时补写（避免光标丢失）
      if (el.innerText === '' && b.text !== '') {
        el.innerText = b.text
        placeCaretAtEnd(el)
      }
      continue
    }
    if (el.innerText !== b.text) el.innerText = b.text
  }
}
watch(blockSignature, () => nextTick(syncBlockTexts), { immediate: true })

// ─── 聚焦 / 失焦：维护 focusedIndex + 浮动按钮位置 ───
function onEditorFocusIn() {
  const el = getCurrentBlockEl()
  focusedIndex.value = el && el.dataset.index != null ? Number(el.dataset.index) : -1
  nextTick(updateResetBtnPos)
}
function onEditorFocusOut() {
  // 延迟检测：点击还原按钮时 activeElement 会短暂离开 editor
  setTimeout(() => {
    if (!editorRef.value || !editorRef.value.contains(document.activeElement)) {
      focusedIndex.value = -1
      resetBtnPos.value = { top: -9999, left: 0 }
    }
  }, 0)
}

function updateResetBtnPos() {
  if (focusedIndex.value < 0 || !editorShellRef.value || !editorRef.value) {
    resetBtnPos.value = { top: -9999, left: 0 }
    return
  }
  const el = editorRef.value.querySelector('[data-index="' + focusedIndex.value + '"]')
  if (!el) return
  const shellRect = editorShellRef.value.getBoundingClientRect()
  const r = el.getBoundingClientRect()
  resetBtnPos.value = { top: r.top - shellRect.top + 2, left: r.right - shellRect.left - 58 }
}

function onResetFocused() {
  if (focusedBlock.value) emit('reset-block', focusedBlock.value.block_id)
}

// ─── 暴露给 App.vue：从右栏摘要定位到左栏对应 block（滚动 + 高亮）───
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

onMounted(() => {
  window.addEventListener('resize', updateResetBtnPos)
})
onUnmounted(() => {
  window.removeEventListener('resize', updateResetBtnPos)
  if (syncTimer) clearTimeout(syncTimer)
})

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

    <!-- 文档正文：单一 contenteditable 容器 -->
    <div class="flex-1 overflow-y-auto px-10 py-8 relative" @scroll="updateResetBtnPos">
      <div v-if="!loaded" class="mt-10 max-w-xl mx-auto">
        <div class="text-center">
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
            输入飞书文档 URL 加载，或从最近访问中选一份
          </p>
          <button
            @click="$emit('open-search')"
            class="mt-3 px-3 py-1.5 rounded text-[13px] font-medium transition-colors inline-flex items-center gap-1"
            :style="{
              background: 'var(--color-surface-container-high)',
              color: 'var(--color-primary)',
            }"
          >
            <span class="material-symbols-outlined text-[16px]">search</span>
            搜索文档
          </button>
        </div>

        <!-- 最近访问 -->
        <div v-if="recentDocs.length > 0" class="mt-8">
          <div
            class="flex items-center gap-1.5 mb-3 text-[12px] font-medium uppercase tracking-wide"
            :style="{ color: 'var(--color-on-surface-variant)' }"
          >
            <span class="material-symbols-outlined text-[15px]">history</span>
            最近访问
          </div>
          <div class="flex flex-col gap-1.5">
            <div
              v-for="doc in recentDocs"
              :key="doc.url"
              class="group flex items-center gap-2 px-3 py-2 rounded cursor-pointer transition-colors"
              :style="{
                background: 'var(--color-surface-container-lowest)',
                border: '1px solid var(--color-outline-variant)',
              }"
              @click="$emit('load-recent', doc.url)"
            >
              <span
                class="material-symbols-outlined text-[18px] shrink-0"
                :style="{ color: 'var(--color-primary)' }"
                >description</span
              >
              <span
                class="flex-1 min-w-0 text-[13px] truncate"
                :style="{ color: 'var(--color-on-surface)' }"
                :title="doc.title"
                >{{ doc.title }}</span
              >
              <button
                aria-label="移除"
                class="shrink-0 p-1 rounded-full opacity-0 group-hover:opacity-100 transition-opacity hover:bg-[var(--color-surface-container-high)]"
                :style="{ color: 'var(--color-on-surface-variant)' }"
                @click.stop="$emit('remove-recent', doc.url)"
              >
                <span class="material-symbols-outlined text-[15px]">close</span>
              </button>
            </div>
          </div>
        </div>
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

      <!--
        单一 contenteditable：所有 block 均为容器直接子元素。
        - 可编辑块：无 contenteditable 属性（继承 true），文本由 JS 同步（避免 Vue 绑定覆盖光标）。
        - 只读块：contenteditable="false" 非编辑岛屿。
        - suggestion 卡片：同样作为 contenteditable="false" 岛屿紧跟对应 block。
          （spec 原文「容器外部」在单一 contenteditable + 「跟在对应 block 后面」约束下不可行，
          非编辑岛屿是保持视觉顺序的唯一可行方式，语义等价于「不参与编辑文本流」。）
      -->
      <div v-else class="max-w-3xl mx-auto">
        <div ref="editorShellRef" class="editor-shell markdown-body">
          <div
            ref="editorRef"
            contenteditable="true"
            spellcheck="false"
            class="editor-surface"
            @keydown="onKeydown"
            @input="onInput"
            @focusin="onEditorFocusIn"
            @focusout="onEditorFocusOut"
          >
            <template v-for="(block, i) in blocks" :key="block.block_id || ('i-' + i)">
              <!-- 可编辑块：空壳元素，文本由 syncBlockTexts 写入 -->
              <component
                v-if="isEditable(block.kind)"
                :is="tagFor(block.kind)"
                :id="'doc-block-' + i"
                :data-block-id="block.block_id"
                :data-kind="block.kind"
                :data-index="i"
                class="editable-content"
                :class="['kind-' + block.kind, { 'is-edited': block.edited, 'doc-block--highlight': highlightedIndex === i }]"
              />

              <!-- 只读：文档标题 -->
              <h1
                v-else-if="block.kind === 'title'"
                :id="'doc-block-' + i"
                :data-block-id="block.block_id"
                :data-kind="block.kind"
                :data-index="i"
                contenteditable="false"
                class="kind-title readonly-title"
                :class="{ 'doc-block--highlight': highlightedIndex === i }"
                :title="'文档标题，只读'"
              >{{ block.text }}</h1>

              <!-- 只读：hr 分隔线 -->
              <div
                v-else-if="block.kind === 'hr'"
                :id="'doc-block-' + i"
                :data-block-id="block.block_id"
                :data-kind="block.kind"
                :data-index="i"
                contenteditable="false"
                class="readonly-hr"
                :class="{ 'doc-block--highlight': highlightedIndex === i }"
              >
                <hr />
              </div>

              <!-- 只读占位：table/figure/img/callout/grid/bookmark/cite -->
              <div
                v-else
                :id="'doc-block-' + i"
                :data-block-id="block.block_id"
                :data-kind="block.kind"
                :data-index="i"
                contenteditable="false"
                class="readonly-block"
                :class="{ 'doc-block--highlight': highlightedIndex === i }"
              >
                <span class="material-symbols-outlined readonly-icon">{{ iconFor(block.kind) }}</span>
                <span class="readonly-label">{{ labelFor(block.kind) }}</span>
                <span class="readonly-text">{{ truncate(block.text, 60) }}</span>
              </div>

              <!-- 待处理建议预览（接受/拒绝）：非编辑岛屿，紧跟对应 block -->
              <div
                v-if="block.suggestion && block.suggestion.state === 'pending'"
                contenteditable="false"
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
            </template>
          </div>

          <!-- 浮动还原按钮：仅对聚焦的已编辑块显示 -->
          <button
            v-if="focusedBlock && focusedBlock.edited"
            class="reset-btn reset-btn--floating"
            :style="{ top: resetBtnPos.top + 'px', left: resetBtnPos.left + 'px' }"
            title="还原该块为加载时的内容"
            @mousedown.prevent="onResetFocused"
          >
            <span class="material-symbols-outlined text-[15px]">restart_alt</span>还原
          </button>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
/* 单一 contenteditable 容器 */
.editor-shell {
  position: relative;
}
.editor-surface {
  outline: none;
}
/* 可编辑块在块流中的纵向间距（覆盖 .editable-content 的 margin:0 -6px） */
.editor-surface > .editable-content {
  display: block;
  margin: 0.3em -6px;
}

.doc-block--highlight {
  box-shadow: 0 0 0 2px var(--color-primary);
  border-radius: 4px;
}

/* 旧逐 block 布局样式（保留以兼容，部分已不再使用） */
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
.readonly-title {
  color: var(--color-on-surface);
  cursor: default;
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
/* 浮动还原按钮：覆盖 margin-top，改为绝对定位 */
.reset-btn--floating {
  position: absolute;
  z-index: 5;
  margin-top: 0;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.1);
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
  margin: 0.3em 0;
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

/* 建议预览卡片（非编辑岛屿） */
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
