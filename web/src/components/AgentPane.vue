<script setup>
import { ref } from 'vue'

const props = defineProps({
  loaded: { type: Boolean, required: true },
  running: { type: Boolean, default: false },
  instruction: { type: String, required: true },
  agentText: { type: String, default: '' },
  agentThinking: { type: String, default: '' },
  replacements: { type: Array, default: () => [] },
})
const emit = defineEmits([
  'update:instruction',
  'chat',
  'quick-action',
  'reject',
  'accept',
])

const thinkingOpen = ref(false)

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

    <!-- 输出流 -->
    <div class="flex-1 overflow-y-auto p-6 flex flex-col gap-3">
      <!-- 空状态 -->
      <div
        v-if="!agentThinking && !agentText && replacements.length === 0 && !running"
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

      <!-- Thinking Card -->
      <div
        v-if="agentThinking || running"
        class="rounded-lg overflow-hidden border"
        :style="{
          background: 'var(--color-thinking-gray)',
          borderColor: 'var(--color-outline-variant)',
        }"
      >
        <button
          @click="thinkingOpen = !thinkingOpen"
          class="w-full flex items-center justify-between p-3 text-left transition-colors hover:bg-[var(--color-surface-variant)]"
        >
          <span
            class="flex items-center gap-2 text-[13px]"
            style="font-family: 'JetBrains Mono', ui-monospace, monospace"
            :style="{ color: 'var(--color-on-surface-variant)' }"
          >
            <span
              class="material-symbols-outlined text-[16px]"
              :class="{ spin: running }"
              :style="{ color: 'var(--color-primary)' }"
              >sync</span
            >
            {{ running ? '正在分析文档语义...' : '思考过程（已完成）' }}
          </span>
          <span
            class="material-symbols-outlined transition-colors"
            :style="{ color: 'var(--color-outline)' }"
          >
            {{ thinkingOpen ? 'expand_less' : 'expand_more' }}
          </span>
        </button>
        <div
          v-show="thinkingOpen && agentThinking"
          class="p-4 text-[13px] whitespace-pre-wrap"
          style="font-family: 'JetBrains Mono', ui-monospace, monospace"
          :style="{
            background: 'var(--color-surface-container-lowest)',
            color: 'var(--color-on-surface-variant)',
            borderTop: '1px solid var(--color-outline-variant)',
          }"
        >{{ agentThinking }}</div>
      </div>

      <!-- Agent 回复气泡 -->
      <div v-if="agentText" class="flex gap-3 fade-in">
        <div
          class="w-8 h-8 rounded-full flex items-center justify-center shrink-0"
          :style="{
            background: 'var(--color-primary-container)',
            color: 'var(--color-on-primary-container)',
          }"
        >
          <span class="material-symbols-outlined text-[20px]">smart_toy</span>
        </div>
        <div
          class="rounded-lg rounded-tl-none p-4 shadow-sm max-w-[85%] border"
          :style="{
            background: 'var(--color-surface)',
            borderColor: 'var(--color-outline-variant)',
          }"
        >
          <p
            class="whitespace-pre-wrap text-[15px]"
            :style="{ color: 'var(--color-on-surface)' }"
          >{{ agentText }}</p>
        </div>
      </div>

      <!-- Diff Cards -->
      <div
        v-if="replacements.length > 0"
        class="flex flex-col gap-4 mt-2 pl-11"
      >
        <div
          v-for="(r, i) in replacements"
          :key="i"
          class="rounded-lg overflow-hidden fade-in"
          :style="{
            background: 'var(--color-surface)',
            border: '1px solid rgba(99, 14, 212, 0.3)',
            boxShadow: '0 4px 12px rgba(99, 14, 212, 0.06)',
          }"
        >
          <!-- header -->
          <div
            class="px-4 py-3 flex items-center justify-between"
            :style="{
              background: 'rgba(124, 58, 237, 0.05)',
              borderBottom: '1px solid var(--color-outline-variant)',
            }"
          >
            <div class="flex items-center gap-2">
              <span
                class="material-symbols-outlined text-[18px]"
                :style="{ color: 'var(--color-primary)' }"
                >edit_note</span
              >
              <h4
                class="font-semibold text-[16px]"
                style="font-family: 'Hanken Grotesk', sans-serif"
                :style="{ color: 'var(--color-on-surface)' }"
              >
                修改建议 #{{ i + 1 }}
              </h4>
            </div>
            <span
              v-if="r.reason"
              class="px-2 py-0.5 rounded-sm border text-[11px] uppercase font-bold tracking-wider"
              :style="{
                background: 'rgba(99, 14, 212, 0.1)',
                color: 'var(--color-primary)',
                borderColor: 'rgba(99, 14, 212, 0.2)',
              }"
            >
              {{ r.reason }}
            </span>
          </div>

          <!-- diff -->
          <div
            class="p-4 leading-relaxed"
            style="
              font-family: 'JetBrains Mono', ui-monospace, monospace;
              font-size: 13px;
            "
          >
            <div class="diff-removed p-2 rounded mb-2 flex items-start gap-2">
              <span class="material-symbols-outlined text-[16px] mt-0.5 shrink-0"
                >remove</span
              >
              <pre class="whitespace-pre-wrap flex-1 m-0 font-mono">{{ r.pattern }}</pre>
            </div>
            <div class="diff-added p-2 rounded flex items-start gap-2">
              <span class="material-symbols-outlined text-[16px] mt-0.5 shrink-0"
                >add</span
              >
              <pre class="whitespace-pre-wrap flex-1 m-0 font-mono">{{ r.content }}</pre>
            </div>
          </div>

          <!-- actions -->
          <div
            class="px-4 py-3 flex justify-end gap-2"
            :style="{
              background: 'var(--color-surface-container-lowest)',
              borderTop: '1px solid var(--color-outline-variant)',
            }"
          >
            <button
              @click="$emit('reject', i)"
              class="px-3 py-1 rounded transition-colors text-[13px] hover:bg-[var(--color-surface-variant)]"
              :style="{ color: 'var(--color-on-surface-variant)' }"
            >
              拒绝
            </button>
            <button
              @click="$emit('accept', i)"
              class="px-3 py-1 rounded transition-colors text-[13px]"
              :style="{
                background: 'var(--color-primary)',
                color: 'var(--color-on-primary)',
              }"
            >
              保留
            </button>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>
