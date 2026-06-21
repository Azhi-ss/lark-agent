<script setup>
defineProps({
  modelValue: { type: String, required: true },
  loading: { type: Boolean, default: false },
})
defineEmits(['update:modelValue', 'load', 'open-settings', 'open-help', 'open-search'])
</script>

<template>
  <header
    class="h-16 shrink-0 flex items-center justify-between px-6 border-b z-50"
    :style="{
      background: 'var(--color-surface)',
      borderColor: 'var(--color-outline-variant)',
    }"
  >
    <!-- 左：标题 + Pro 徽章 -->
    <div class="flex items-center gap-3">
      <h1
        class="text-xl font-bold flex items-center gap-2"
        style="
          font-family: 'Hanken Grotesk', sans-serif;
          color: var(--color-primary);
        "
      >
        Feishu Weekly AI
        <span
          class="text-[10px] uppercase font-bold px-1.5 py-0.5 rounded-sm tracking-wider"
          :style="{
            background: 'var(--color-primary-container)',
            color: 'var(--color-on-primary)',
          }"
        >
          Pro
        </span>
      </h1>
    </div>

    <!-- 中：URL 输入 + 加载按钮 -->
    <div class="flex-1 max-w-2xl mx-8 relative">
      <div
        class="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none"
      >
        <span
          class="material-symbols-outlined text-[20px]"
          :style="{ color: 'var(--color-outline)' }"
          >link</span
        >
      </div>
      <input
        :value="modelValue"
        @input="$emit('update:modelValue', $event.target.value)"
        @keydown.enter="$emit('load')"
        type="text"
        placeholder="请输入飞书文档链接（docx / wiki URL）..."
        class="block w-full pl-10 pr-32 py-2 border rounded text-sm focus:outline-none focus:ring-2 transition-shadow"
        :style="{
          background: 'var(--color-surface)',
          borderColor: 'var(--color-outline-variant)',
          color: 'var(--color-on-surface)',
        }"
      />
      <div class="absolute inset-y-0 right-0 flex items-center pr-1">
        <button
          @click="$emit('load')"
          :disabled="loading"
          class="px-4 py-1.5 rounded text-sm font-medium transition-colors disabled:opacity-50"
          :style="{
            background: 'var(--color-primary)',
            color: 'var(--color-on-primary)',
          }"
        >
          {{ loading ? '加载中...' : '加载文档' }}
        </button>
      </div>
    </div>

    <!-- 右：图标按钮 -->
    <div
      class="flex items-center gap-2"
      :style="{ color: 'var(--color-on-surface-variant)' }"
    >
      <slot name="tabs" />
      <button
        aria-label="搜索文档"
        @click="$emit('open-search')"
        class="p-2 rounded-full transition-colors hover:bg-[var(--color-surface-container-high)]"
      >
        <span class="material-symbols-outlined">search</span>
      </button>
      <button
        aria-label="设置"
        @click="$emit('open-settings')"
        class="p-2 rounded-full transition-colors hover:bg-[var(--color-surface-container-high)]"
      >
        <span class="material-symbols-outlined">settings</span>
      </button>
      <button
        aria-label="帮助"
        @click="$emit('open-help')"
        class="p-2 rounded-full transition-colors hover:bg-[var(--color-surface-container-high)]"
      >
        <span class="material-symbols-outlined">help</span>
      </button>
    </div>
  </header>
</template>
