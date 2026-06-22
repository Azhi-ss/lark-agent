import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import DocPane from './DocPane.vue'

const baseProps = {
  loaded: true,
  docMeta: { document_id: 'doc-1', revision_id: 1, block_count: 0 },
  loadError: '',
  recentDocs: [],
}

function mountDocPane(blocks) {
  return mount(DocPane, {
    props: {
      ...baseProps,
      docMeta: { ...baseProps.docMeta, block_count: blocks.length },
      blocks,
    },
  })
}

describe('DocPane 渲染', () => {
  it('渲染单一 contenteditable 容器', () => {
    const wrapper = mountDocPane([{ block_id: 'b1', kind: 'p', text: '正文' }])

    const surface = wrapper.find('.editor-surface')
    expect(surface.exists()).toBe(true)
    expect(surface.attributes('contenteditable')).toBe('true')
  })

  it('可编辑 block 渲染 data 属性和正确标签', () => {
    const blocks = [
      { block_id: 'h1', kind: 'h1', text: '一级' },
      { block_id: 'h2', kind: 'h2', text: '二级' },
      { block_id: 'h3', kind: 'h3', text: '三级' },
      { block_id: 'h4', kind: 'h4', text: '四级' },
      { block_id: 'pre', kind: 'pre', text: '代码' },
      { block_id: 'p', kind: 'p', text: '正文' },
      { block_id: 'ul', kind: 'ul', text: '列表' },
      { block_id: 'ol', kind: 'ol', text: '有序' },
    ]
    const wrapper = mountDocPane(blocks)

    const expectedTags = ['H1', 'H2', 'H3', 'H4', 'PRE', 'DIV', 'DIV', 'DIV']
    blocks.forEach((block, index) => {
      const el = wrapper.find(`[data-block-id="${block.block_id}"]`)
      expect(el.exists()).toBe(true)
      expect(el.element.tagName).toBe(expectedTags[index])
      expect(el.attributes('data-kind')).toBe(block.kind)
      expect(el.attributes('data-index')).toBe(String(index))
    })
  })

  it('只读 block 带 contenteditable false', () => {
    const blocks = [
      { block_id: 'title', kind: 'title', text: '标题' },
      { block_id: 'table', kind: 'table', text: '表格内容' },
      { block_id: 'hr', kind: 'hr', text: '' },
    ]
    const wrapper = mountDocPane(blocks)

    for (const block of blocks) {
      expect(wrapper.find(`[data-block-id="${block.block_id}"]`).attributes('contenteditable')).toBe(
        'false',
      )
    }
  })

  it('pending suggestion 卡片渲染为不可编辑元素', () => {
    const wrapper = mountDocPane([
      {
        block_id: 'b1',
        kind: 'p',
        text: '正文',
        suggestion: { state: 'pending', reason: '建议理由', content: '建议正文' },
      },
    ])

    const card = wrapper.find('.suggestion-card')
    expect(card.exists()).toBe(true)
    expect(card.attributes('contenteditable')).toBe('false')
    expect(card.text()).toContain('建议理由')
    expect(card.text()).toContain('建议正文')
  })
})
