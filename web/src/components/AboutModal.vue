<script setup>
/**
 * 关于 / 帮助浮层：说明产品用途、前置条件、关键设计与风险提示。
 * 纯静态展示，无数据交互。
 */
defineProps({
  open: { type: Boolean, default: false },
})
const emit = defineEmits(['close'])
</script>

<template>
  <Teleport to="body">
    <div
      v-if="open"
      class="fixed inset-0 z-[100] flex items-center justify-center"
      :style="{ background: 'rgba(0,0,0,0.4)' }"
      @click.self="emit('close')"
    >
      <div
        class="w-[520px] max-w-[92vw] rounded-xl shadow-2xl overflow-hidden"
        :style="{
          background: 'var(--color-surface)',
          border: '1px solid var(--color-outline-variant)',
        }"
      >
        <!-- 标题 -->
        <div
          class="px-6 py-4 flex items-center justify-between border-b"
          :style="{ borderColor: 'var(--color-outline-variant)' }"
        >
          <h3
            class="text-lg font-semibold flex items-center gap-2"
            style="font-family: 'Hanken Grotesk', sans-serif"
            :style="{ color: 'var(--color-on-surface)' }"
          >
            <span class="material-symbols-outlined" :style="{ color: 'var(--color-primary)' }"
              >help</span
            >
            关于 & 帮助
          </h3>
          <button
            aria-label="关闭"
            class="p-1 rounded-full transition-colors hover:bg-[var(--color-surface-container-high)]"
            :style="{ color: 'var(--color-on-surface-variant)' }"
            @click="emit('close')"
          >
            <span class="material-symbols-outlined">close</span>
          </button>
        </div>

        <!-- 内容 -->
        <div
          class="px-6 py-5 text-[14px] leading-relaxed flex flex-col gap-4 max-h-[70vh] overflow-y-auto"
          :style="{ color: 'var(--color-on-surface)' }"
        >
          <p :style="{ color: 'var(--color-on-surface-variant)' }">
            通过可视化界面，用 AI 提炼和修改飞书周报文档，确认 diff 后写回飞书。
          </p>

          <div class="flex flex-col gap-1.5">
            <h4 class="font-semibold text-[14px]">两种模式</h4>
            <ul class="list-disc pl-5 flex flex-col gap-1" :style="{ color: 'var(--color-on-surface-variant)' }">
              <li><strong>单文档编辑</strong>：加载一份飞书周报 → 输入指令 → Agent 产出替换建议 → 确认 diff → 写回飞书</li>
              <li><strong>方案构建</strong>：加载多份上下文文档 → 对话 → Agent 产出/迭代结构化方案 → 导出 .md</li>
            </ul>
          </div>

          <div class="flex flex-col gap-1.5">
            <h4 class="font-semibold text-[14px]">前置条件</h4>
            <ul class="list-disc pl-5 flex flex-col gap-1" :style="{ color: 'var(--color-on-surface-variant)' }">
              <li><code>lark-cli</code> 已安装并 <code>auth login</code>（user 身份）</li>
              <li>LLM 接入：右上角 ⚙️ 设置中配置 Base URL / API Key / Model</li>
            </ul>
          </div>

          <div
            class="rounded-lg p-3 flex gap-2 items-start"
            :style="{
              background: 'var(--color-thinking-gray)',
              border: '1px solid var(--color-outline-variant)',
            }"
          >
            <span class="material-symbols-outlined text-[18px] shrink-0" :style="{ color: 'var(--color-secondary)' }"
              >warning</span
            >
            <p class="text-[13px]" :style="{ color: 'var(--color-on-surface-variant)' }">
              <strong>安全提示</strong>：AI 生成内容在写回飞书前请务必审阅。可在环境变量
              <code>LARK_WRITEBACK=0</code> 全局禁用写回（仅模拟）。
            </p>
          </div>

          <p class="text-[12px]" :style="{ color: 'var(--color-outline)' }">
            注意：设置中的 LLM 配置仅存于后端进程内存，重启后端会恢复为环境变量默认值。
          </p>
        </div>

        <!-- 操作 -->
        <div
          class="px-6 py-4 flex justify-end border-t"
          :style="{
            background: 'var(--color-surface-container)',
            borderColor: 'var(--color-outline-variant)',
          }"
        >
          <button
            class="px-4 py-2 rounded text-sm font-medium transition-colors"
            :style="{
              background: 'var(--color-primary)',
              color: 'var(--color-on-primary)',
            }"
            @click="emit('close')"
          >
            知道了
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
