<script setup>
import { ref, watch } from 'vue'
import { getLlmSettings, saveLlmSettings, testLlmSettings } from '../api.js'

/**
 * LLM 接入设置弹窗。
 * - base_url / model / api_key / auth_token 均明文读写（GET 回明文）
 * - api_key / auth_token 默认密码框遮罩，点眼睛图标切换显示/隐藏
 * - 保存：密码框留空 → null（不改保留原值）；有输入 → 覆盖；空串 → 清空
 * - 测试连接：打开面板自动测一次 + 手动可重测；用面板当前输入的临时配置（不落库）
 * - 延迟分级着色：绿 <1000ms / 黄 1000–3000ms / 红 >3000ms
 */
const props = defineProps({
  open: { type: Boolean, default: false },
})
const emit = defineEmits(['close', 'saved'])

const baseUrl = ref('')
const model = ref('')
const apiKey = ref('')
const authToken = ref('')

// 显示/隐藏切换
const showApiKey = ref(false)
const showAuthToken = ref(false)

const loading = ref(false)
const saving = ref(false)
const error = ref('')
const status = ref('')

// 检测结果
const testing = ref(false)
const testResult = ref(null) // {ok, latency_ms, error_type, detail}

const ERROR_TYPE_LABELS = {
  network: '网络不通',
  auth: '鉴权失败',
  model: '模型名无效',
  rate_limit: '触发限流',
  unknown: '失败',
}

// 延迟分级：绿 <1000 / 黄 1000–3000 / 红 >3000
function latencyColor(ms) {
  if (ms == null) return 'var(--color-on-surface-variant)'
  if (ms < 1000) return '#16a34a'
  if (ms <= 3000) return '#d97706'
  return '#dc2626'
}

// 打开时拉取当前配置 + 自动测一次
watch(
  () => props.open,
  async (isOpen) => {
    if (!isOpen) return
    error.value = ''
    status.value = ''
    testResult.value = null
    showApiKey.value = false
    showAuthToken.value = false
    loading.value = true
    try {
      const cfg = await getLlmSettings()
      baseUrl.value = cfg.base_url || ''
      model.value = cfg.model || ''
      apiKey.value = cfg.api_key || ''
      authToken.value = cfg.auth_token || ''
    } catch (e) {
      error.value = e.message
    } finally {
      loading.value = false
    }
    // 自动测一次（用已加载的配置）
    await runTest()
  },
)

async function onSave() {
  if (saving.value) return
  saving.value = true
  error.value = ''
  status.value = ''
  try {
    // 密码框留空 → null（不改）；有输入 → 用新值；空串 → 清空
    const patch = {
      base_url: baseUrl.value,
      model: model.value,
      api_key: apiKey.value === '' ? null : apiKey.value,
      auth_token: authToken.value === '' ? null : authToken.value,
    }
    const cfg = await saveLlmSettings(patch)
    status.value = '已保存'
    emit('saved', cfg)
    setTimeout(() => (status.value = ''), 2000)
  } catch (e) {
    error.value = e.message
  } finally {
    saving.value = false
  }
}

async function runTest() {
  if (testing.value) return
  testing.value = true
  testResult.value = null
  try {
    testResult.value = await testLlmSettings({
      base_url: baseUrl.value,
      api_key: apiKey.value,
      auth_token: authToken.value,
      model: model.value,
    })
  } catch (e) {
    testResult.value = { ok: false, error_type: 'unknown', detail: e.message }
  } finally {
    testing.value = false
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

            <!-- API Key：明文 + 眼睛切换 -->
            <div class="flex flex-col gap-1.5">
              <label class="text-[13px] font-medium" :style="{ color: 'var(--color-on-surface)' }">
                API Key
                <span :style="{ color: 'var(--color-on-surface-variant)' }" class="font-normal">
                  （留空保存=不改，清空全部内容保存=清空）
                </span>
              </label>
              <div class="relative">
                <input
                  v-model="apiKey"
                  :type="showApiKey ? 'text' : 'password'"
                  placeholder="sk-ant-... 或代理凭证"
                  class="w-full px-3 py-2 pr-10 text-sm border rounded focus:outline-none focus:ring-2"
                  :style="{
                    background: 'var(--color-surface-container-lowest)',
                    borderColor: 'var(--color-outline-variant)',
                    color: 'var(--color-on-surface)',
                  }"
                />
                <button
                  type="button"
                  :aria-label="showApiKey ? '隐藏' : '显示'"
                  class="absolute inset-y-0 right-0 pr-3 flex items-center"
                  :style="{ color: 'var(--color-on-surface-variant)' }"
                  @click="showApiKey = !showApiKey"
                >
                  <span class="material-symbols-outlined text-[18px]">{{
                    showApiKey ? 'visibility_off' : 'visibility'
                  }}</span>
                </button>
              </div>
            </div>

            <!-- Auth Token：明文 + 眼睛切换 -->
            <div class="flex flex-col gap-1.5">
              <label class="text-[13px] font-medium" :style="{ color: 'var(--color-on-surface)' }">
                Auth Token
                <span :style="{ color: 'var(--color-on-surface-variant)' }" class="font-normal">
                  （留空保存=不改，清空全部内容保存=清空）
                </span>
              </label>
              <div class="relative">
                <input
                  v-model="authToken"
                  :type="showAuthToken ? 'text' : 'password'"
                  placeholder="代理模式鉴权 token"
                  class="w-full px-3 py-2 pr-10 text-sm border rounded focus:outline-none focus:ring-2"
                  :style="{
                    background: 'var(--color-surface-container-lowest)',
                    borderColor: 'var(--color-outline-variant)',
                    color: 'var(--color-on-surface)',
                  }"
                />
                <button
                  type="button"
                  :aria-label="showAuthToken ? '隐藏' : '显示'"
                  class="absolute inset-y-0 right-0 pr-3 flex items-center"
                  :style="{ color: 'var(--color-on-surface-variant)' }"
                  @click="showAuthToken = !showAuthToken"
                >
                  <span class="material-symbols-outlined text-[18px]">{{
                    showAuthToken ? 'visibility_off' : 'visibility'
                  }}</span>
                </button>
              </div>
              <p class="text-[11px]" :style="{ color: 'var(--color-on-surface-variant)' }">
                代理模式：填 Base URL + Auth Token；官方模式：填 API Key、Base URL 留空。
              </p>
            </div>

            <!-- 测试连接 -->
            <div class="flex flex-col gap-2">
              <button
                :disabled="testing"
                class="self-start px-4 py-2 rounded text-sm font-medium transition-colors flex items-center gap-2 disabled:opacity-50 border"
                :style="{
                  background: 'var(--color-surface-container-lowest)',
                  borderColor: 'var(--color-outline-variant)',
                  color: 'var(--color-on-surface)',
                }"
                @click="runTest"
              >
                <span
                  class="material-symbols-outlined text-[18px]"
                  :class="{ spin: testing }"
                  >{{ testing ? 'sync' : 'network_check' }}</span
                >
                {{ testing ? '检测中...' : '测试连接' }}
              </button>

              <!-- 检测结果 -->
              <div
                v-if="testResult"
                class="rounded-lg px-3 py-2 text-[13px] flex items-center gap-2"
                :style="{
                  background: testResult.ok
                    ? 'rgba(22,163,74,0.08)'
                    : 'rgba(220,38,38,0.08)',
                  border: `1px solid ${
                    testResult.ok ? 'rgba(22,163,74,0.3)' : 'rgba(220,38,38,0.3)'
                  }`,
                }"
              >
                <span
                  class="material-symbols-outlined text-[18px]"
                  :style="{
                    color: testResult.ok ? '#16a34a' : '#dc2626',
                  }"
                  >{{ testResult.ok ? 'check_circle' : 'cancel' }}</span
                >
                <span :style="{ color: 'var(--color-on-surface)' }">
                  <template v-if="testResult.ok">
                    连接正常 · 延迟
                    <strong :style="{ color: latencyColor(testResult.latency_ms) }">
                      {{ testResult.latency_ms }}ms
                    </strong>
                  </template>
                  <template v-else>
                    {{ ERROR_TYPE_LABELS[testResult.error_type] || '失败' }}：{{
                      testResult.detail
                    }}
                  </template>
                </span>
              </div>
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
