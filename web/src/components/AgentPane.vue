<script setup>
import ConversationTimeline from './timeline/ConversationTimeline.vue'

/**
 * AgentPane —— editor 模式右侧 agent 面板。
 * P3：输出区由「Thinking Card + 气泡 + located/unlocated 建议列表」
 * 统一替换为 ConversationTimeline；建议审阅移入 ArtifactDrawer。
 *
 * 保留：顶部指令输入区 + 快捷指令 + 处理按钮（功能不变，视觉对齐飞书协作气质）。
 */
defineProps({
  loaded: { type: Boolean, required: true },
  running: { type: Boolean, default: false },
  instruction: { type: String, required: true },
  timelineItems: { type: Array, default: () => [] },
})
const emit = defineEmits([
  'update:instruction',
  'chat',
  'quick-action',
  'open-artifact',
  'locate',
  'accept',
  'reject',
  'writeback',
  'action',
])

function quick(text) {
  emit('quick-action', text)
}
</script>

<template>
  <section
    class="w-1/2 flex flex-col relative"
    :style="{ background: 'var(--color-app-bg)' }"
  >
    <!-- 指令输入区 -->
    <div
      class="p-6 shrink-0"
      :style="{
        background: 'var(--color-surface)',
        borderBottom: '1px solid var(--color-outline-variant)',
      }"
    >
      <div
        class="rounded-lg border transition-all focus-within:ring-2"
        :style="{
          background: 'var(--color-surface-container-lowest)',
          borderColor: 'var(--color-outline-variant)',
        }"
      >
        <textarea
          :value="instruction"
          @input="$emit('update:instruction', $event.target.value)"
          :disabled="!loaded || running"
          rows="3"
          placeholder="请告诉我你想如何修改这份周报，例如：提炼本周要点 / 精简第二段 / 把语气改正式..."
          class="w-full bg-transparent border-none resize-none focus:outline-none p-4 min-h-[100px] text-[15px] disabled:opacity-60"
          :style="{ color: 'var(--color-on-surface)' }"
        ></textarea>

        <!-- 底部条带：快捷指令 + 处理按钮 -->
        <div
          class="flex items-center justify-between px-4 py-3 rounded-b-lg"
          :style="{
            background: 'var(--color-surface-container)',
            borderTop: '1px solid var(--color-outline-variant)',
          }"
        >
          <div class="flex gap-2">
            <button
              @click="quick('请帮我提炼本周核心要点，在文末追加 “## 本周要点” 摘要段落。')"
              :disabled="!loaded || running"
              class="px-3 py-1 rounded-full text-[13px] transition-colors disabled:opacity-40"
              :style="{
                background: 'var(--color-surface-container-high)',
                color: 'var(--color-on-surface-variant)',
              }"
            >
              总结
            </button>
            <button
              @click="quick('请帮我润色全文语气，使其更正式、专业，但保持原意。')"
              :disabled="!loaded || running"
              class="px-3 py-1 rounded-full text-[13px] transition-colors disabled:opacity-40 border"
              :style="{
                background: 'rgba(99, 14, 212, 0.08)',
                color: 'var(--color-primary)',
                borderColor: 'rgba(99, 14, 212, 0.2)',
              }"
            >
              润色语气
            </button>
          </div>
          <button
            @click="$emit('chat')"
            :disabled="!loaded || running"
            class="px-4 py-1.5 rounded text-sm font-medium transition-colors flex items-center gap-2 disabled:opacity-50"
            :style="{
              background: 'var(--color-primary)',
              color: 'var(--color-on-primary)',
            }"
          >
            <span
              class="material-symbols-outlined text-[18px]"
              :class="{ spin: running }"
            >
              {{ running ? 'sync' : 'magic_button' }}
            </span>
            {{ running ? '处理中...' : '开始处理' }}
          </button>
        </div>
      </div>
    </div>

    <!-- 统一 timeline 输出区 -->
    <div class="flex-1 overflow-y-auto p-6 flex flex-col gap-3">
      <!-- 空态：timeline 为空且非 running -->
      <div
        v-if="timelineItems.length === 0 && !running"
        class="text-center mt-16"
      >
        <span
          class="material-symbols-outlined text-[48px]"
          :style="{ color: 'var(--color-outline-variant)' }"
        >
          smart_toy
        </span>
        <p
          class="mt-3 text-sm"
          :style="{ color: 'var(--color-on-surface-variant)' }"
        >
          {{ loaded ? '输入指令，让 Agent 处理周报' : '请先加载文档' }}
        </p>
      </div>

      <ConversationTimeline
        v-else
        :items="timelineItems"
        :running="running"
        @open-artifact="(id) => emit('open-artifact', id)"
        @action="(id) => emit('action', id)"
        @locate="(p) => emit('locate', p)"
        @accept="(p) => emit('accept', p)"
        @reject="(p) => emit('reject', p)"
        @writeback="(id) => emit('writeback', id)"
      />
    </div>
  </section>
</template>
