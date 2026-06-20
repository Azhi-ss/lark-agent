<script setup>
const props = defineProps({
  loaded: { type: Boolean, required: true },
  docMeta: { type: Object, required: true },
  markdownHtml: { type: String, default: '' },
  loadError: { type: String, default: '' },
})
defineEmits(['open-external'])
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

    <!-- 文档正文 -->
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
        v-else
        class="max-w-3xl mx-auto markdown-body"
        v-html="markdownHtml"
      ></div>
    </div>
  </section>
</template>
