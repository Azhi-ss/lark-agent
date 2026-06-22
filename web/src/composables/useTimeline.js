import { ref } from 'vue'

/**
 * useTimeline —— 统一 timeline 数据模型 + SSE 事件映射。
 *
 * TimelineItem 是判别联合（discriminated union），按 kind 分发：
 *   - user:             { id, kind: 'user', text }
 *   - status:           { id, kind: 'status', label, state: 'active' | 'done' }
 *   - assistant_text:   { id, kind: 'assistant_text', text }
 *   - thinking_summary: { id, kind: 'thinking_summary', text }
 *   - artifact:         { id, kind: 'artifact', artifact: AgentArtifact, isLatest: boolean }
 *   - action_required:  { id, kind: 'action_required', reason }
 *   - error:            { id, kind: 'error', message }
 *   - complete:         { id, kind: 'complete' }
 *
 * 所有变更走不可变替换（spread / map 重建数组），符合全局 immutability 约定，
 * 同时 Vue 3 ref 重新赋值也能正确触发响应式更新。
 */

// 模块级递增 id 计数器：单调递增、可读，且跨多次 createTimeline() 全局唯一。
// 不用 Date.now / Math.random（任务约束）。
let _idCounter = 0
function nextId() {
  _idCounter += 1
  return _idCounter
}

/**
 * 创建一个独立 timeline 实例。
 * @returns {{
 *   items: import('vue').Ref<Array>,
 *   pushUser: (text: string) => void,
 *   pushStatus: (label: string) => void,
 *   pushAssistantTextDelta: (text: string) => void,
 *   pushThinkingDelta: (text: string) => void,
 *   pushArtifact: (artifact: AgentArtifact) => void,
 *   pushActionRequired: (reason: string) => void,
 *   pushError: (message: string) => void,
 *   pushComplete: () => void,
 *   reset: () => void,
 *   markLatestArtifact: () => void,
 * }}
 */
export function createTimeline() {
  const items = ref([])

  function pushUser(text) {
    items.value = [...items.value, { id: nextId(), kind: 'user', text }]
  }

  /**
   * 推入一个状态步骤（默认 active）。
   * 产品语义：新阶段开始意味着上一阶段完成 —— 自动把上一条 active status 置为 done，
   * 形成「流水线推进」视觉。最后一条 active 由 pushComplete 收尾。
   */
  function pushStatus(label) {
    const promoted = items.value.map((it) =>
      it.kind === 'status' && it.state === 'active'
        ? { ...it, state: 'done' }
        : it,
    )
    items.value = [
      ...promoted,
      { id: nextId(), kind: 'status', label, state: 'active' },
    ]
  }

  /** 增量累积 assistant_text：末条同 kind 则续写，否则新增一条。 */
  function pushAssistantTextDelta(text) {
    if (!text) return
    const last = items.value[items.value.length - 1]
    if (last && last.kind === 'assistant_text') {
      items.value = items.value.map((it, i) =>
        i === items.value.length - 1 ? { ...it, text: it.text + text } : it,
      )
    } else {
      items.value = [
        ...items.value,
        { id: nextId(), kind: 'assistant_text', text },
      ]
    }
  }

  /** 增量累积 thinking_summary：末条同 kind 则续写，否则新增一条。 */
  function pushThinkingDelta(text) {
    if (!text) return
    const last = items.value[items.value.length - 1]
    if (last && last.kind === 'thinking_summary') {
      items.value = items.value.map((it, i) =>
        i === items.value.length - 1 ? { ...it, text: it.text + text } : it,
      )
    } else {
      items.value = [
        ...items.value,
        { id: nextId(), kind: 'thinking_summary', text },
      ]
    }
  }

  /** 把所有 artifact 的 isLatest 置 false（pushArtifact 内部调用，也可单独调用）。 */
  function markLatestArtifact() {
    items.value = items.value.map((it) =>
      it.kind === 'artifact' ? { ...it, isLatest: false } : it,
    )
  }

  /**
   * 推入一个 artifact，默认 isLatest=true。
   * 先把之前所有 artifact 的 isLatest 置 false，再新增一条 isLatest=true。
   */
  function pushArtifact(artifact) {
    markLatestArtifact()
    items.value = [
      ...items.value,
      { id: nextId(), kind: 'artifact', artifact, isLatest: true },
    ]
  }

  function pushActionRequired(reason) {
    items.value = [
      ...items.value,
      { id: nextId(), kind: 'action_required', reason },
    ]
  }

  function pushError(message) {
    items.value = [
      ...items.value,
      { id: nextId(), kind: 'error', message },
    ]
  }

  /** 收尾：把残留的 active status 置 done，再推入 complete 标记。 */
  function pushComplete() {
    const closed = items.value.map((it) =>
      it.kind === 'status' && it.state === 'active'
        ? { ...it, state: 'done' }
        : it,
    )
    items.value = [...closed, { id: nextId(), kind: 'complete' }]
  }

  function reset() {
    items.value = []
  }

  return {
    items,
    pushUser,
    pushStatus,
    pushAssistantTextDelta,
    pushThinkingDelta,
    pushArtifact,
    pushActionRequired,
    pushError,
    pushComplete,
    reset,
    markLatestArtifact,
  }
}

/**
 * 把后端 SSE 产品语义事件 { type, data } 映射成 timeline push 调用。
 *
 * artifact 事件「先调 ctx 回调再 push artifact item」—— 让集成层先产生业务副作用
 * （定位 block / 更新方案画布），再把 artifact 落进 timeline 展示。
 *
 * @param {{ type: string, data: any }} ev SSE 事件
 * @param {ReturnType<typeof createTimeline>} timeline createTimeline() 返回值
 * @param {{ onDocumentEdits?: (payload: any) => void, onSolution?: (payload: any) => void }} ctx
 *   业务副作用回调；payload 即 artifact.payload（document_edits=replacements 包，solution=方案包）
 */
export function mapSseEvent(ev, timeline, ctx = {}) {
  const { type, data } = ev || {}
  switch (type) {
    case 'status':
      timeline.pushStatus(data?.label)
      break
    case 'assistant_text':
      timeline.pushAssistantTextDelta(data?.text)
      break
    case 'thinking_summary':
      timeline.pushThinkingDelta(data?.text)
      break
    case 'artifact': {
      const artifact = {
        artifact_type: data?.artifact_type,
        title: data?.title ?? '',
        summary: data?.summary ?? '',
        payload: data?.payload,
      }
      // 先回调（业务副作用），再 push（展示）
      if (
        artifact.artifact_type === 'document_edits' &&
        typeof ctx.onDocumentEdits === 'function'
      ) {
        ctx.onDocumentEdits(artifact.payload)
      } else if (
        artifact.artifact_type === 'solution' &&
        typeof ctx.onSolution === 'function'
      ) {
        ctx.onSolution(artifact.payload)
      }
      timeline.pushArtifact(artifact)
      break
    }
    case 'action_required':
      timeline.pushActionRequired(data?.reason)
      break
    case 'error':
      timeline.pushError(data?.message ?? '未知错误')
      break
    case 'complete':
      timeline.pushComplete()
      break
    default:
      // 未知事件类型静默忽略，避免破坏整条流
      break
  }
}
