import { describe, expect, it } from 'vitest'
import {
  createTimeline,
  mapSseEvent,
} from './useTimeline'

/**
 * useTimeline 纯逻辑验证：push 累积、isLatest 管理、status 推进、SSE 映射。
 * 不测 Vue 响应式触发（ref 行为由 Vue 保证），只测数据形态正确性。
 */
describe('useTimeline', () => {
  it('pushUser / pushStatus / pushError / pushComplete 产生正确 kind', () => {
    const t = createTimeline()
    t.pushUser('hi')
    t.pushStatus('分析中')
    t.pushError('boom')
    t.pushComplete()

    expect(t.items.value.map((x) => x.kind)).toEqual([
      'user',
      'status',
      'error',
      'complete',
    ])
    expect(t.items.value[0]).toMatchObject({ kind: 'user', text: 'hi' })
    // pushComplete 收尾 → state 变 done
    expect(t.items.value[1]).toMatchObject({
      kind: 'status',
      label: '分析中',
      state: 'done',
    })
    expect(t.items.value[2]).toMatchObject({ kind: 'error', message: 'boom' })
    expect(t.items.value[3]).toMatchObject({ kind: 'complete' })
  })

  it('id 单调递增且唯一', () => {
    const t = createTimeline()
    t.pushUser('a')
    t.pushUser('b')
    t.pushUser('c')
    const ids = t.items.value.map((x) => x.id)
    expect(ids).toEqual([...ids].sort((a, b) => a - b))
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('pushAssistantTextDelta: 同 kind 末条累积，否则新增', () => {
    const t = createTimeline()
    t.pushAssistantTextDelta('Hello')
    t.pushAssistantTextDelta(', ')
    t.pushAssistantTextDelta('world')
    // 全部累积到同一条
    expect(t.items.value).toHaveLength(1)
    expect(t.items.value[0].text).toBe('Hello, world')

    // 插入一条 user 后再 delta，应新增一条 assistant_text
    t.pushUser('ok')
    t.pushAssistantTextDelta('Again')
    expect(t.items.value).toHaveLength(3)
    expect(t.items.value[2].kind).toBe('assistant_text')
    expect(t.items.value[2].text).toBe('Again')
  })

  it('pushThinkingDelta: 同 kind 末条累积', () => {
    const t = createTimeline()
    t.pushThinkingDelta('step1 ')
    t.pushThinkingDelta('step2')
    expect(t.items.value).toHaveLength(1)
    expect(t.items.value[0].text).toBe('step1 step2')
  })

  it('空 delta 不产生新条目', () => {
    const t = createTimeline()
    t.pushAssistantTextDelta('')
    t.pushAssistantTextDelta(undefined)
    t.pushThinkingDelta('')
    expect(t.items.value).toHaveLength(0)
  })

  it('pushStatus 自动把上一条 active 置 done（流水线推进）', () => {
    const t = createTimeline()
    t.pushStatus('阶段一')
    t.pushStatus('阶段二')
    t.pushStatus('阶段三')
    const statuses = t.items.value.filter((x) => x.kind === 'status')
    expect(statuses.map((x) => x.state)).toEqual([
      'done',
      'done',
      'active',
    ])
  })

  it('pushComplete 把残留 active status 收尾为 done', () => {
    const t = createTimeline()
    t.pushStatus('阶段一')
    t.pushStatus('阶段二') // 阶段一 → done, 阶段二 active
    t.pushComplete()
    const statuses = t.items.value.filter((x) => x.kind === 'status')
    expect(statuses.every((x) => x.state === 'done')).toBe(true)
    expect(t.items.value.at(-1).kind).toBe('complete')
  })

  it('pushArtifact: 新 artifact isLatest=true，旧的置 false', () => {
    const t = createTimeline()
    t.pushArtifact({ artifact_type: 'solution', title: 'v1', summary: '', payload: {} })
    t.pushArtifact({ artifact_type: 'solution', title: 'v2', summary: '', payload: {} })
    t.pushArtifact({ artifact_type: 'solution', title: 'v3', summary: '', payload: {} })

    const arts = t.items.value.filter((x) => x.kind === 'artifact')
    expect(arts).toHaveLength(3)
    expect(arts.map((x) => x.isLatest)).toEqual([false, false, true])
    expect(arts[2].artifact.title).toBe('v3')
  })

  it('markLatestArtifact 单独调用清空所有 isLatest', () => {
    const t = createTimeline()
    t.pushArtifact({ artifact_type: 'solution', title: 'v1', summary: '', payload: {} })
    t.pushArtifact({ artifact_type: 'solution', title: 'v2', summary: '', payload: {} })
    t.markLatestArtifact()
    const arts = t.items.value.filter((x) => x.kind === 'artifact')
    expect(arts.every((x) => x.isLatest === false)).toBe(true)
  })

  it('reset 清空 items', () => {
    const t = createTimeline()
    t.pushUser('a')
    t.pushStatus('s')
    t.reset()
    expect(t.items.value).toHaveLength(0)
  })
})

describe('mapSseEvent', () => {
  it('status / assistant_text / thinking_summary / complete / error 正确映射', () => {
    const t = createTimeline()
    mapSseEvent({ type: 'status', data: { label: '分析上下文' } }, t)
    mapSseEvent({ type: 'thinking_summary', data: { text: '正在' } }, t)
    mapSseEvent({ type: 'thinking_summary', data: { text: '思考' } }, t)
    mapSseEvent({ type: 'assistant_text', data: { text: '你好' } }, t)
    mapSseEvent({ type: 'error', data: { message: '挂了' } }, t)
    mapSseEvent({ type: 'complete', data: {} }, t)

    expect(t.items.value.map((x) => x.kind)).toEqual([
      'status',
      'thinking_summary',
      'assistant_text',
      'error',
      'complete',
    ])
    expect(t.items.value[1].text).toBe('正在思考')
    expect(t.items.value[2].text).toBe('你好')
    // complete 收尾 active status
    expect(t.items.value[0].state).toBe('done')
  })

  it('artifact: 先调 ctx 回调再 push artifact item', () => {
    const t = createTimeline()
    const calls = []
    const ctx = {
      onDocumentEdits: (payload) => calls.push(['doc', payload]),
      onSolution: (payload) => calls.push(['sol', payload]),
    }
    const docEv = {
      type: 'artifact',
      data: {
        artifact_type: 'document_edits',
        title: '编辑',
        summary: '2 处',
        payload: { replacements: [{ pattern: 'a', content: 'b', reason: 'r' }] },
      },
    }
    mapSseEvent(docEv, t, ctx)

    // 回调先于 push：此时 timeline 已有 artifact item
    expect(calls).toHaveLength(1)
    expect(calls[0][0]).toBe('doc')
    expect(calls[0][1]).toEqual(docEv.data.payload)
    expect(t.items.value[0].kind).toBe('artifact')
    expect(t.items.value[0].artifact.artifact_type).toBe('document_edits')
    expect(t.items.value[0].isLatest).toBe(true)

    // 再来一个 solution artifact → onSolution 触发，旧 artifact isLatest=false
    const solEv = {
      type: 'artifact',
      data: {
        artifact_type: 'solution',
        title: 'S',
        summary: '',
        payload: { title: 'S', markdown: '# x', summary: '' },
      },
    }
    mapSseEvent(solEv, t, ctx)
    expect(calls[1][0]).toBe('sol')
    const arts = t.items.value.filter((x) => x.kind === 'artifact')
    expect(arts.map((x) => x.isLatest)).toEqual([false, true])
  })

  it('artifact 缺失字段时给默认值（title/summary 空串，payload 透传）', () => {
    const t = createTimeline()
    mapSseEvent(
      { type: 'artifact', data: { artifact_type: 'solution' } },
      t,
      {},
    )
    expect(t.items.value[0].artifact).toEqual({
      artifact_type: 'solution',
      title: '',
      summary: '',
      payload: undefined,
    })
  })

  it('action_required 映射 reason', () => {
    const t = createTimeline()
    mapSseEvent(
      { type: 'action_required', data: { reason: 'writeback_confirmation' } },
      t,
    )
    expect(t.items.value[0]).toMatchObject({
      kind: 'action_required',
      reason: 'writeback_confirmation',
    })
  })

  it('error 缺失 message 时兜底「未知错误」', () => {
    const t = createTimeline()
    mapSseEvent({ type: 'error', data: {} }, t)
    expect(t.items.value[0].message).toBe('未知错误')
  })

  it('未知事件类型静默忽略，不破坏 timeline', () => {
    const t = createTimeline()
    t.pushUser('x')
    mapSseEvent({ type: 'whatever', data: {} }, t)
    mapSseEvent({ type: undefined, data: null }, t)
    expect(t.items.value).toHaveLength(1)
  })
})
