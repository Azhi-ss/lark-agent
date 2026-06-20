<script setup>
import { ref, watch } from 'vue'
import { getLlmSettings, saveLlmSettings } from '../api.js'

/**
 * LLM 接入设置弹窗。
 * - base_url / model 明文读写
 * - api_key / auth_token 用密码框：留空=不改（提交 null），有内容才覆盖
 * - GET 不回明文，只用占位符提示是否已配置
 */
const props = defineProps({
  open: { type: Boolean, default: false },
})
const emit = defineEmits(['close', 'saved'])

const baseUrl = ref('')
const model = ref('')
const apiKey = ref('')
const authToken = ref('')
const hasApiKey = ref(false)
const hasAuthToken = ref(false)

const loading = ref(false)
const saving = ref(false)
const error = ref('')
const status = ref('')

// 打开时拉取当前配置
watch(
  () => props.open,
  async (isOpen) => {
    if (!isOpen) return
    error.value = ''
    status.value = ''
    apiKey.value = ''
    authToken.value = ''
    loading.value = true
    try {
      const cfg = await getLlmSettings()
      baseUrl.value = cfg.base_url || ''
      model.value = cfg.model || ''
      hasApiKey.value = cfg.has_api_key
      hasAuthToken.value = cfg.has_auth_token
    } catch (e) {
      error.value = e.message
    } finally {
      loading.value = false
    }
  },
)

async function onSave() {
  if (saving.value) return
  saving.value = true
  error.value = ''
  status.value = ''
  try {
    // 密码框留空 → null（不改）；有输入 → 用新值
    const patch = {
      base_url: baseUrl.value,
      model: model.value,
      api_key: apiKey.value === '' ? null : apiKey.value,
      auth_token: authToken.value === '' ? null : authToken.value,
    }
    const cfg = await saveLlmSettings(patch)
    hasApiKey.value = cfg.has_api_key
    hasAuthToken.value = cfg.has_auth_token
    apiKey.value = ''
    authToken.value = ''
    status.value = '已保存'
    emit('saved', cfg)
    setTimeout(() => (status.value = ''), 2000)
  } catch (e) {
    error.value = e.message
  } finally {
    saving.value = false
  }
}
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
        class="w-[480px] max-w-[92vw] rounded-xl shadow-2xl overflow-hidden"
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
              >tune</span
            >
            LLM 接入设置
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

        <!-- 表单 -->
        <div class="px-6 py-5 flex flex-col gap-4">
          <p v-if="loading" class="text-sm" :style="{ color: 'var(--color-on-surface-variant)' }">
            加载中...
          </p>
          <template v-else>
            <div class="flex flex-col gap-1.5">
              <label class="text-[13px] font-medium" :style="{ color: 'var(--color-on-surface)' }">
                Base URL
                <span :style="{ color: 'var(--color-on-surface-variant)' }" class="font-normal">
                  （代理地址，留空走官方 Anthropic）
                </span>
              </label>
              <input
                v-model="baseUrl"
                type="text"
                placeholder="https://your-proxy.example.com"
                class="px-3 py-2 text-sm border rounded focus:outline-none focus:ring-2"
                :style="{
                  background: 'var(--color-surface-container-lowest)',
                  borderColor: 'var(--color-outline-variant)',
                  color: 'var(--color-on-surface)',
                }"
              />
            </div>

            <div class="flex flex-col gap-1.5">
              <label class="text-[13px] font-medium" :style="{ color: 'var(--color-on-surface)' }">
                Model
              </label>
              <input
                v-model="model"
                type="text"
                placeholder="claude-sonnet-4-6"
                class="px-3 py-2 text-sm border rounded focus:outline-none focus:ring-2"
                :style="{
                  background: 'var(--color-surface-container-lowest)',
                  borderColor: 'var(--color-outline-variant)',
                  color: 'var(--color-on-surface)',
                }"
              />
            </div>

            <div class="flex flex-col gap-1.5">
              <label class="text-[13px] font-medium" :style="{ color: 'var(--color-on-surface)' }">
                API Key
                <span
                  v-if="hasApiKey"
                  class="font-normal text-[12px] ml-1"
                  :style="{ color: 'var(--color-secondary)' }"
                  >（已配置，留空表示不改）</span
                >
              </label>
              <input
                v-model="apiKey"
                type="password"
                :placeholder="hasApiKey ? '已配置（留空不改）' : 'sk-ant-... 或代理凭证'"
                class="px-3 py-2 text-sm border rounded focus:outline-none focus:ring-2"
                :style="{
                  background: 'var(--color-surface-container-lowest)',
                  borderColor: 'var(--color-outline-variant)',
                  color: 'var(--color-on-surface)',
                }"
              />
            </div>

            <div class="flex flex-col gap-1.5">
              <label class="text-[13px] font-medium" :style="{ color: 'var(--color-on-surface)' }">
                Auth Token
                <span
                  v-if="hasAuthToken"
                  class="font-normal text-[12px] ml-1"
                  :style="{ color: 'var(--color-secondary)' }"
                  >（已配置，留空表示不改）</span
                >
              </label>
              <input
                v-model="authToken"
                type="password"
                :placeholder="hasAuthToken ? '已配置（留空不改）' : '代理模式鉴权 token'"
                class="px-3 py-2 text-sm border rounded focus:outline-none focus:ring-2"
                :style="{
                  background: 'var(--color-surface-container-lowest)',
                  borderColor: 'var(--color-outline-variant)',
                  color: 'var(--color-on-surface)',
                }"
              />
              <p class="text-[11px]" :style="{ color: 'var(--color-on-surface-variant)' }">
                代理模式：填 Base URL + Auth Token；官方模式：填 API Key、Base URL 留空。
              </p>
            </div>

            <p v-if="error" class="text-[13px]" :style="{ color: 'var(--color-error)' }">
              {{ error }}
            </p>
            <p v-if="status" class="text-[13px]" :style="{ color: 'var(--color-primary)' }">
              {{ status }}
            </p>
          </template>
        </div>

        <!-- 操作 -->
        <div
          class="px-6 py-4 flex justify-end gap-2 border-t"
          :style="{
            background: 'var(--color-surface-container)',
            borderColor: 'var(--color-outline-variant)',
          }"
        >
          <button
            class="px-4 py-2 rounded text-sm transition-colors hover:bg-[var(--color-surface-container-high)]"
            :style="{ color: 'var(--color-on-surface-variant)' }"
            @click="emit('close')"
          >
            取消
          </button>
          <button
            :disabled="loading || saving"
            class="px-4 py-2 rounded text-sm font-medium transition-colors disabled:opacity-50"
            :style="{
              background: 'var(--color-primary)',
              color: 'var(--color-on-primary)',
            }"
            @click="onSave"
          >
            {{ saving ? '保存中...' : '保存' }}
          </button>
        </div>
      </div>
    </div>
  </Teleport>
</template>
