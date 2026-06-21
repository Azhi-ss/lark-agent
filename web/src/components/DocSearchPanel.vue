<script setup>
import { ref, computed } from 'vue'
import { searchDocs } from '../api.js'

/**
 * 通用文档搜索面板。
 * - 回车 / 点搜索按钮才搜（不边输边搜）
 * - 结果列表用 v-html 渲染高亮（后端已锁死只允许 <mark>，其余转义）
 * - 多选 + 批量导入；emit('import', urls)，落点由父组件决定
 * - 选中状态跨查询累积：换关键词重搜只清 results / pageToken，保留 selected
 *
 * Props:
 *   - compact: 紧凑模式（嵌入侧栏 vs 独立浮层）
 * Emits:
 *   - import(urls: string[])  导入选中的文档 URL
 */
defineProps({
  compact: { type: Boolean, default: false },
})
const emit = defineEmits(['import'])

const query = ref('')
const results = ref([])
const selected = ref(new Set())
const hasMore = ref(false)
const pageToken = ref('')
const loading = ref(false)
const error = ref('')
const searched = ref(false)

// 当前结果命中 selected 的数量（用于区分"本次结果中" vs "跨查询")
const selectedInCurrent = computed(() => {
  let n = 0
  for (const r of results.value) {
    if (r.url && selected.value.has(r.url)) n++
  }
  return n
})
const selectedCount = computed(() => selected.value.size)
const selectedCrossQuery = computed(() => selectedCount.value - selectedInCurrent.value)

async function doSearch(reset = true) {
  const q = query.value.trim()
  if (!q || loading.value) return
  if (reset) {
    // 跨查询保留 selected，只清 results / pageToken
    results.value = []
    pageToken.value = ''
  }
  loading.value = true
  error.value = ''
  try {
    const res = await searchDocs(q, {
      page_size: 15,
      page_token: reset ? undefined : pageToken.value,
    })
    results.value = reset ? res.results : [...results.value, ...res.results]
    hasMore.value = res.has_more
    pageToken.value = res.page_token || ''
    searched.value = true
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function onEnter() {
  doSearch(true)
}

function loadMore() {
  doSearch(false)
}

function toggle(url) {
  if (!url) return
  const next = new Set(selected.value)
  if (next.has(url)) next.delete(url)
  else next.add(url)
  selected.value = next
}

function clearSelected() {
  selected.value = new Set()
}

function onImport() {
  const urls = [...selected.value]
  if (urls.length === 0) return
  emit('import', urls)
  // 导入后清空全部跨查询选中
  selected.value = new Set()
}
</script>

<template>
  <div
    class="flex flex-col gap-3 h-full min-h-0"
    :class="compact ? '' : 'p-4'"
  >
    <!-- 搜索框 -->
    <div class="flex gap-2 shrink-0">
      <input
        v-model="query"
        @keydown.enter="onEnter"
        type="text"
        placeholder="搜索飞书文档（回车搜索）"
        class="flex-1 px-3 py-1.5 text-[13px] border rounded focus:outline-none focus:ring-2"
        :style="{
          background: 'var(--color-surface-container-lowest)',
          borderColor: 'var(--color-outline-variant)',
          color: 'var(--color-on-surface)',
        }"
      />
      <button
        @click="onEnter"
        :disabled="loading || !query.trim()"
        class="px-3 py-1.5 rounded text-[13px] font-medium transition-colors flex items-center gap-1 disabled:opacity-50"
        :style="{
          background: 'var(--color-primary)',
          color: 'var(--color-on-primary)',
        }"
      >
        <span class="material-symbols-outlined text-[16px]">{{
          loading ? 'sync' : 'search'
        }}</span>
        {{ loading ? '搜索中' : '搜索' }}
      </button>
    </div>

    <p
      v-if="error"
      class="text-[12px] shrink-0"
      :style="{ color: 'var(--color-error)' }"
    >
      {{ error }}
    </p>

    <!-- 跨查询选中提示（常驻，selectedCount > 0 时渲染） -->
    <div
      v-if="selectedCount > 0"
      class="flex items-center justify-between gap-2 shrink-0 text-[12px]"
      :style="{ color: 'var(--color-on-surface-variant)' }"
    >
      <span class="truncate">
        已选
        <span
          class="font-semibold"
          :style="{ color: 'var(--color-on-surface)' }"
          >{{ selectedCount }}</span
        >
        份
        <span class="opacity-80">
          （当前结果 {{ selectedInCurrent }} · 跨查询
          <span
            class="font-semibold"
            :style="{ color: 'var(--color-primary)' }"
            >{{ selectedCrossQuery }}</span
          >）
        </span>
      </span>
      <button
        type="button"
        class="shrink-0 px-2 py-0.5 rounded transition-colors hover:bg-[var(--color-surface-container-high)]"
        :style="{ color: 'var(--color-primary)' }"
        @click="clearSelected"
      >
        清空
      </button>
    </div>

    <!-- 结果列表（内部滚动容器） -->
    <div
      v-if="results.length > 0"
      class="results-scroll flex-1 min-h-0 overflow-y-auto flex flex-col gap-2 pr-1"
    >
      <div
        v-for="(r, i) in results"
        :key="r.url || i"
        class="rounded border p-2.5 cursor-pointer transition-colors"
        :style="{
          background: selected.has(r.url)
            ? 'var(--color-secondary-container)'
            : 'var(--color-surface-container-lowest)',
          borderColor: selected.has(r.url)
            ? 'var(--color-primary)'
            : 'var(--color-outline-variant)',
        }"
        @click="toggle(r.url)"
      >
        <div class="flex items-start gap-2">
          <input
            type="checkbox"
            :checked="selected.has(r.url)"
            class="mt-0.5 shrink-0"
            @click.stop="toggle(r.url)"
          />
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2">
              <span
                class="material-symbols-outlined text-[15px] shrink-0"
                :style="{ color: 'var(--color-primary)' }"
                >{{ r.entity_type === 'WIKI' ? 'menu_book' : 'description' }}</span
              >
              <!-- v-html: 后端已锁死仅 <mark> 标签，其余转义 -->
              <span
                class="text-[13px] font-medium truncate"
                :style="{ color: 'var(--color-on-surface)' }"
                v-html="r.title || '(无标题)'"
              ></span>
              <span
                v-if="r.doc_type"
                class="text-[10px] px-1 rounded shrink-0"
                :style="{
                  background: 'var(--color-surface-container-high)',
                  color: 'var(--color-on-surface-variant)',
                }"
                >{{ r.doc_type }}</span
              >
            </div>
            <p
              v-if="r.summary"
              class="text-[12px] mt-1 line-clamp-2"
              :style="{ color: 'var(--color-on-surface-variant)' }"
              v-html="r.summary"
            ></p>
            <div
              class="flex items-center gap-3 mt-1 text-[11px]"
              :style="{ color: 'var(--color-outline)' }"
            >
              <span v-if="r.owner">{{ r.owner }}</span>
              <span v-if="r.updated_at">{{ r.updated_at.slice(0, 10) }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 分页：放在滚动容器内末尾 -->
      <button
        v-if="hasMore"
        @click="loadMore"
        :disabled="loading"
        class="self-center text-[12px] px-3 py-1 rounded transition-colors hover:bg-[var(--color-surface-container)] disabled:opacity-50"
        :style="{ color: 'var(--color-primary)' }"
      >
        {{ loading ? '加载中...' : '加载更多' }}
      </button>
    </div>

    <!-- 空状态 -->
    <div
      v-else-if="searched && !loading"
      class="text-center py-6 text-[13px] shrink-0"
      :style="{ color: 'var(--color-on-surface-variant)' }"
    >
      无搜索结果
    </div>

    <!-- 导入按钮（固定在底部，不进滚动） -->
    <div
      v-if="selected.size > 0"
      class="flex items-center justify-end shrink-0 pt-1"
    >
      <button
        @click="onImport"
        class="px-4 py-1.5 rounded text-[13px] font-medium transition-colors flex items-center gap-1"
        :style="{
          background: 'var(--color-secondary)',
          color: 'var(--color-on-secondary)',
        }"
      >
        <span class="material-symbols-outlined text-[16px]">download</span>
        导入到上下文（{{ selected.size }}）
      </button>
    </div>
  </div>
</template>

<style scoped>
.line-clamp-2 {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* 与 Material You 主题一致的细滚动条 */
.results-scroll::-webkit-scrollbar {
  width: 6px;
}
.results-scroll::-webkit-scrollbar-track {
  background: transparent;
}
.results-scroll::-webkit-scrollbar-thumb {
  background: var(--color-outline-variant);
  border-radius: 3px;
}
.results-scroll::-webkit-scrollbar-thumb:hover {
  background: var(--color-outline);
}
.results-scroll {
  scrollbar-width: thin;
  scrollbar-color: var(--color-outline-variant) transparent;
}
</style>
