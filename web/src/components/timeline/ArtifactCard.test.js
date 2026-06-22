import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import ArtifactCard from './ArtifactCard.vue'

/**
 * timeline/ArtifactCard 叶子组件测试。
 *
 * 锁定 emit 名与 payload 形态，防止 drawer→timeline→集成层链路回归：
 * - openArtifact(id) / exportSolution(id) 传裸 id
 * - locate({ id, index, pattern })  传完整对象（集成层读 pattern 解析 blockId）
 * - accept/reject({ pattern, index }) 与 drawer DocumentEditsArtifact 对齐
 * - isLatest=false 时 accept/reject 禁用（旧 artifact 高风险动作保护）
 */
function findButtonByText(wrapper, text) {
  return wrapper.findAll('button').find((b) => b.text().includes(text))
}

const docEdits = {
  artifact_type: 'document_edits',
  title: '修改建议',
  summary: '1 处',
  payload: {
    replacements: [{ pattern: '旧文本', content: '新文本', reason: '润色' }],
    final_text: '新文本',
  },
}

const solution = {
  artifact_type: 'solution',
  title: '方案',
  summary: 'v1',
  payload: { title: '方案', markdown: '# 标题', summary: 'v1' },
}

describe('ArtifactCard - document_edits', () => {
  it('「查看完整」emit openArtifact(id) 裸 id', async () => {
    const wrapper = mount(ArtifactCard, {
      props: { id: 11, artifact: docEdits, isLatest: true },
    })
    await findButtonByText(wrapper, '查看完整').trigger('click')
    expect(wrapper.emitted('openArtifact')[0]).toEqual([11])
  })

  it('「定位到文档」emit locate({ id, index, pattern })', async () => {
    const wrapper = mount(ArtifactCard, {
      props: { id: 11, artifact: docEdits, isLatest: true },
    })
    await findButtonByText(wrapper, '定位到文档').trigger('click')
    expect(wrapper.emitted('locate')[0][0]).toEqual({
      id: 11,
      index: 0,
      pattern: '旧文本',
    })
  })

  it('「采纳」emit accept({ pattern, index })', async () => {
    const wrapper = mount(ArtifactCard, {
      props: { id: 11, artifact: docEdits, isLatest: true },
    })
    await findButtonByText(wrapper, '采纳').trigger('click')
    expect(wrapper.emitted('accept')[0][0]).toEqual({ pattern: '旧文本', index: 0 })
  })

  it('「忽略」emit reject({ pattern, index })', async () => {
    const wrapper = mount(ArtifactCard, {
      props: { id: 11, artifact: docEdits, isLatest: true },
    })
    await findButtonByText(wrapper, '忽略').trigger('click')
    expect(wrapper.emitted('reject')[0][0]).toEqual({ pattern: '旧文本', index: 0 })
  })

  it('isLatest=false：采纳/忽略禁用，定位与查看完整仍可用', () => {
    // findAll('button') 返回 VueWrapper，读 disabled 走 .element.disabled
    const wrapper = mount(ArtifactCard, {
      props: { id: 11, artifact: docEdits, isLatest: false },
    })
    expect(findButtonByText(wrapper, '采纳').element.disabled).toBe(true)
    expect(findButtonByText(wrapper, '忽略').element.disabled).toBe(true)
    expect(findButtonByText(wrapper, '定位到文档').element.disabled).toBe(false)
    expect(findButtonByText(wrapper, '查看完整').element.disabled).toBe(false)
  })

  it('isLatest=true：渲染「最新」徽标', () => {
    const wrapper = mount(ArtifactCard, {
      props: { id: 11, artifact: docEdits, isLatest: true },
    })
    expect(wrapper.text()).toContain('最新')
  })

  it('空 replacements 渲染「无替换建议」', () => {
    const empty = { ...docEdits, payload: { replacements: [], final_text: '' } }
    const wrapper = mount(ArtifactCard, {
      props: { id: 11, artifact: empty, isLatest: true },
    })
    expect(wrapper.text()).toContain('无替换建议')
  })
})

describe('ArtifactCard - solution', () => {
  it('「导出 .md」emit exportSolution(id) 裸 id', async () => {
    const wrapper = mount(ArtifactCard, {
      props: { id: 22, artifact: solution, isLatest: true },
    })
    await findButtonByText(wrapper, '导出 .md').trigger('click')
    expect(wrapper.emitted('exportSolution')[0]).toEqual([22])
  })

  it('solution 也渲染采纳/忽略按钮（isLatest 控制）', () => {
    const wrapper = mount(ArtifactCard, {
      props: { id: 22, artifact: solution, isLatest: false },
    })
    expect(findButtonByText(wrapper, '采纳').element.disabled).toBe(true)
    expect(findButtonByText(wrapper, '忽略').element.disabled).toBe(true)
  })

  it('渲染 markdown 预览', () => {
    const wrapper = mount(ArtifactCard, {
      props: { id: 22, artifact: solution, isLatest: true },
    })
    expect(wrapper.text()).toContain('# 标题')
  })
})
