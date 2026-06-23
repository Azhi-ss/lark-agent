<script setup>
import { ref, computed } from 'vue'

/**
 * document_edits artifact 详情：replacements 列表 + 底部写回按钮。
 * - 每条 replacement 渲染为卡片：reason 标题 / pattern 片段（mono 截断）/ content 预览
 * - 每条都有：定位 / 复制内容（接受/拒绝仅 isLatest 启用）
 * - emit locate/accept/reject 传 { pattern, index }，由 ArtifactDrawer 透传
 *   blockId 由集成层在 locate 时解析 pattern → blockId，本组件不感知 blockId
 */
const props = defineProps({
  payload: { type: Object, default: () => ({}) }, // { replacements, final_text }
  isLatest: { type: Boolean, default: false },
})
const emit = defineEmits(['locate', 'accept', 'reject', 'writeback'])

const replacements = computed(() => props.payload?.replacements || [])
const copiedIdx = ref(-1)

function truncate(s, n = 80) {
  if (!s) return ''
  return s.length > n ? s.slice(0, n) + '…' : s
}

function onLocate(r, i) {
  emit('locate', { pattern: r.pattern, index: i })
}
function onAccept(r, i) {
  emit('accept', { pattern: r.pattern, index: i })
}
function onReject(r, i) {
  emit('reject', { pattern: r.pattern, index: i })
}

function copyContent(text, i) {
  if (!navigator.clipboard) return
  navigator.clipboard
    .writeText(text || '')
    .then(() => {
      copiedIdx.value = i
      window.setTimeout(() => {
        if (copiedIdx.value === i) copiedIdx.value = -1
      }, 1500)
    })
    .catch(() => {})
}
</script>

<template>
  <div class="flex-1 flex flex-col min-h-0">
    <!-- 滚动区：只读提示 + 建议列表 -->
    <div class="flex-1 overflow-y-auto p-4 flex flex-col gap-3">
      <!-- 旧版本只读提示 -->
      <div
        v-if="!isLatest"
        class="flex items-center gap-2 px-3 py-2 rounded text-[12px]"
        :style="{
          background: 'var(--color-surface-container)',
          color: 'var(--color-on-surface-variant)',
        }"
      >
        <span class="material-symbols-outlined text-[16px]">lock</span>
        旧版本只读：仅可定位查看，接受/拒绝/写回已禁用
      </div>

      <!-- 建议卡片 -->
      <div
        v-for="(r, i) in replacements"
        :key="i"
        class="rounded-lg overflow-hidden border fade-in"
        :style="{
          background: 'var(--color-surface-container-lowest)',
          borderColor: 'var(--color-outline-variant)',
        }"
      >
        <!-- reason 标题 -->
        <div
          class="px-4 py-2.5 flex items-center gap-2"
          :style="{ borderBottom: '1px solid var(--color-outline-variant)' }"
        >
          <span
            class="material-symbols-outlined text-[18px] shrink-0"
            :style="{ color: 'var(--color-primary)' }"
          >edit_note</span>
          <span
            class="text-[13px] font-semibold truncate flex-1"
            :style="{ color: 'var(--color-on-surface)' }"
          >{{ r.reason || '修改建议' }}</span>
        </div>

        <!-- pattern 片段（mono 截断） -->
        <div
          class="px-4 py-2 text-[12px] truncate"
          style="font-family: 'JetBrains Mono', ui-monospace, monospace"
          :style="{ color: 'var(--color-on-surface-variant)' }"
        >匹配片段：{{ truncate(r.pattern, 80) }}</div>

        <!-- content 预览 -->
        <pre
          class="m-0 px-4 py-3 text-[12px] whitespace-pre-wrap"
          style="font-family: 'JetBrains Mono', ui-monospace, monospace"
          :style="{
            color: 'var(--color-on-surface)',
            background: 'var(--color-surface)',
          }"
        >{{ r.content }}</pre>

        <!-- 操作按钮 -->
        <div
          class="px-4 py-2.5 flex items-center justify-end gap-2 flex-wrap"
          :style="{
            background: 'var(--color-surface-container-lowest)',
            borderTop: '1px solid var(--color-outline-variant)',
          }"
        >
          <!-- 复制内容（常驻；未定位建议也可复制） -->
          <button
            type="button"
            @click="copyContent(r.content, i)"
            class="px-3 py-1 rounded transition-colors text-[13px] flex items-center gap-1"
            :style="{
              background: copiedIdx === i ? 'var(--color-success-surface)' : 'var(--color-surface-container-high)',
              color: copiedIdx === i ? 'var(--color-success-text)' : 'var(--color-on-surface-variant)',
            }"
          >
            <span class="material-symbols-outlined text-[16px]">content_copy</span>
            {{ copiedIdx === i ? '已复制' : '复制内容' }}
          </button>

          <!-- 定位 / 接受 / 拒绝 -->
          <button
            type="button"
            @click="onLocate(r, i)"
            class="px-3 py-1 rounded transition-colors text-[13px] flex items-center gap-1"
            :style="{
              background: 'var(--color-surface-container-high)',
              color: 'var(--color-on-surface-variant)',
            }"
          >
            <span class="material-symbols-outlined text-[16px]">my_location</span>
            定位
          </button>
          <button
            type="button"
            @click="onAccept(r, i)"
            :disabled="!isLatest"
            :title="!isLatest ? '旧版本只读' : ''"
            class="px-3 py-1 rounded transition-colors text-[13px] flex items-center gap-1 disabled:opacity-40 disabled:cursor-not-allowed"
            :style="{
              background: 'var(--color-secondary)',
              color: 'var(--color-on-secondary)',
            }"
          >
            <span class="material-symbols-outlined text-[16px]">check</span>
            接受
          </button>
          <button
            type="button"
            @click="onReject(r, i)"
            :disabled="!isLatest"
            :title="!isLatest ? '旧版本只读' : ''"
            class="px-3 py-1 rounded transition-colors text-[13px] flex items-center gap-1 disabled:opacity-40 disabled:cursor-not-allowed"
            :style="{
              background: 'var(--color-surface-container-high)',
              color: 'var(--color-danger-text)',
            }"
          >
            <span class="material-symbols-outlined text-[16px]">close</span>
            拒绝
          </button>
        </div>
      </div>

      <!-- 空态 -->
      <div
        v-if="replacements.length === 0"
        class="text-center py-8 text-[13px]"
        :style="{ color: 'var(--color-on-surface-variant)' }"
      >
        暂无修改建议
      </div>
    </div>

    <!-- 底部写回飞书按钮（固定） -->
    <div
      v-if="replacements.length > 0"
      class="shrink-0 p-4 border-t"
      :style="{
        background: 'var(--color-surface)',
        borderColor: 'var(--color-outline-variant)',
      }"
    >
      <button
        type="button"
        @click="emit('writeback')"
        :disabled="!isLatest"
        class="w-full px-4 py-2.5 rounded-lg text-[14px] font-medium transition-colors flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
        :style="{
          background: 'var(--color-secondary)',
          color: 'var(--color-on-secondary)',
        }"
      >
        <span class="material-symbols-outlined text-[18px]">cloud_upload</span>
        {{ isLatest ? '写回飞书文档' : '写回已禁用（旧版本只读）' }}
      </button>
    </div>
  </div>
</template>
