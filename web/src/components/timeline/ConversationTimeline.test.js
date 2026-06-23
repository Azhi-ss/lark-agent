import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ConversationTimeline from './ConversationTimeline.vue'
import ArtifactCard from './ArtifactCard.vue'

/**
 * ConversationTimeline 容器测试：
 * - artifact item 渲染 ArtifactCard 并透传 props
 * - 点击「查看完整」触发 openArtifact(id)（透传 ArtifactCard）
 * - action_required(writeback_confirmation) 内联渲染，确认按钮触发 writeback(id)
 * - solution artifact 点击「导出 .md」触发 exportSolution(id)
 */
function findButtonByText(wrapper, text) {
  return wrapper.findAll('button').find((b) => b.text().includes(text))
}

const docArtifactItem = {
  id: 101,
  kind: 'artifact',
  artifact: {
    artifact_type: 'document_edits',
    title: '修改建议',
    summary: '2 处',
    payload: {
      replacements: [{ pattern: '旧文本', content: '新文本', reason: '润色' }],
      final_text: '新文本',
    },
  },
  isLatest: true,
}

const solutionArtifactItem = {
  id: 202,
  kind: 'artifact',
  artifact: {
    artifact_type: 'solution',
    title: '方案',
    summary: 'v1',
    payload: { title: '方案', markdown: '# 标题', summary: 'v1' },
  },
  isLatest: true,
}

describe('ConversationTimeline', () => {
  it('artifact item 渲染 ArtifactCard 并透传 id / isLatest', () => {
    const wrapper = mount(ConversationTimeline, {
      props: { items: [docArtifactItem] },
    })
    const card = wrapper.findComponent(ArtifactCard)
    expect(card.exists()).toBe(true)
    expect(card.props('id')).toBe(101)
    expect(card.props('isLatest')).toBe(true)
  })

  it('点击 ArtifactCard「查看完整」触发 openArtifact(item.id)', async () => {
    const wrapper = mount(ConversationTimeline, {
      props: { items: [docArtifactItem] },
    })
    const btn = findButtonByText(wrapper, '查看完整')
    expect(btn).toBeTruthy()
    await btn.trigger('click')

    const ev = wrapper.emitted('openArtifact')
    expect(ev).toBeTruthy()
    expect(ev[0]).toEqual([101])
  })

  it('action_required(writeback_confirmation) 内联渲染，确认按钮触发 writeback(id)', async () => {
    const wrapper = mount(ConversationTimeline, {
      props: {
        items: [
          { id: 7, kind: 'action_required', reason: 'writeback_confirmation' },
        ],
      },
    })
    const confirmBtn = findButtonByText(wrapper, '确认写回')
    expect(confirmBtn).toBeTruthy()
    await confirmBtn.trigger('click')
    expect(wrapper.emitted('writeback')).toBeTruthy()
    expect(wrapper.emitted('writeback')[0]).toEqual([7])
  })

  it('solution artifact 点击「导出 .md」触发 exportSolution(id)', async () => {
    const wrapper = mount(ConversationTimeline, {
      props: { items: [solutionArtifactItem] },
    })
    const exportBtn = findButtonByText(wrapper, '导出 .md')
    expect(exportBtn).toBeTruthy()
    await exportBtn.trigger('click')
    expect(wrapper.emitted('exportSolution')).toBeTruthy()
    expect(wrapper.emitted('exportSolution')[0]).toEqual([202])
  })

  // === 透传链路测试（锁死 drawer→timeline→集成层 emit 名与 payload）===
  // 这些用例针对 review 暴露的 CRITICAL#2：timeline ArtifactCard 的
  // locate/accept/reject payload 形态必须与 App.vue handler 读取的 payload.pattern 对齐。

  it('document_edits「定位到文档」触发 locate({ id, index, pattern })', async () => {
    const wrapper = mount(ConversationTimeline, {
      props: { items: [docArtifactItem] },
    })
    const locateBtn = findButtonByText(wrapper, '定位到文档')
    expect(locateBtn).toBeTruthy()
    await locateBtn.trigger('click')

    const ev = wrapper.emitted('locate')
    expect(ev).toBeTruthy()
    // payload 含 pattern，App.vue onArtifactLocate 读 payload.pattern 解析 blockId
    expect(ev[0][0]).toMatchObject({ id: 101, index: 0, pattern: '旧文本' })
  })

  it('document_edits「采纳」触发 accept({ pattern, index })（isLatest=true）', async () => {
    const wrapper = mount(ConversationTimeline, {
      props: { items: [docArtifactItem] },
    })
    const acceptBtn = findButtonByText(wrapper, '采纳')
    expect(acceptBtn).toBeTruthy()
    expect(acceptBtn.element.disabled).toBe(false)
    await acceptBtn.trigger('click')

    const ev = wrapper.emitted('accept')
    expect(ev).toBeTruthy()
    // payload 与 drawer DocumentEditsArtifact 对齐为 { pattern, index }
    expect(ev[0][0]).toEqual({ pattern: '旧文本', index: 0 })
  })

  it('document_edits「忽略」触发 reject({ pattern, index })（isLatest=true）', async () => {
    const wrapper = mount(ConversationTimeline, {
      props: { items: [docArtifactItem] },
    })
    const rejectBtn = findButtonByText(wrapper, '忽略')
    expect(rejectBtn).toBeTruthy()
    await rejectBtn.trigger('click')

    const ev = wrapper.emitted('reject')
    expect(ev).toBeTruthy()
    expect(ev[0][0]).toEqual({ pattern: '旧文本', index: 0 })
  })

  it('isLatest=false 时 采纳/忽略 按钮禁用（旧 artifact 高风险动作不可点）', () => {
    const wrapper = mount(ConversationTimeline, {
      props: { items: [{ ...docArtifactItem, isLatest: false }] },
    })
    const acceptBtn = findButtonByText(wrapper, '采纳')
    const rejectBtn = findButtonByText(wrapper, '忽略')
    expect(acceptBtn.element.disabled).toBe(true)
    expect(rejectBtn.element.disabled).toBe(true)
    // 定位与查看完整不受 isLatest 影响
    expect(findButtonByText(wrapper, '定位到文档').element.disabled).toBe(false)
    expect(findButtonByText(wrapper, '查看完整').element.disabled).toBe(false)
  })

  it('action_required(overwrite_solution_confirmation) 确认触发 overwriteSolution(id)', async () => {
    const wrapper = mount(ConversationTimeline, {
      props: {
        items: [
          { id: 9, kind: 'action_required', reason: 'overwrite_solution_confirmation' },
        ],
      },
    })
    const confirmBtn = findButtonByText(wrapper, '覆盖方案')
    expect(confirmBtn).toBeTruthy()
    await confirmBtn.trigger('click')
    expect(wrapper.emitted('overwriteSolution')).toBeTruthy()
    expect(wrapper.emitted('overwriteSolution')[0]).toEqual([9])
  })

  it('action_required「取消」触发 dismiss(id) 且卡片收起', async () => {
    const items = [
      { id: 8, kind: 'action_required', reason: 'writeback_confirmation' },
    ]
    const wrapper = mount(ConversationTimeline, { props: { items } })
    const cancelBtn = findButtonByText(wrapper, '取消')
    expect(cancelBtn).toBeTruthy()
    await cancelBtn.trigger('click')
    expect(wrapper.emitted('dismiss')).toBeTruthy()
    expect(wrapper.emitted('dismiss')[0]).toEqual([8])
    // 卡片标记 dismissed 后不再渲染
    expect(items[0].dismissed).toBe(true)
    await wrapper.vm.$nextTick()
    expect(findButtonByText(wrapper, '取消')).toBeFalsy()
  })
})
