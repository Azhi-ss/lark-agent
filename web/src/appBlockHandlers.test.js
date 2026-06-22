import { describe, expect, it, vi } from 'vitest'
import {
  onBlocksChanged,
  onChangeBlockKind,
  onMergeBlocks,
  onSplitBlock,
} from './appBlockHandlers.js'

const textToBlockXml = vi.fn((kind, text) => `<${kind}>${text}</${kind}>`)

function baseBlocks() {
  return [
    {
      block_id: 'a',
      kind: 'p',
      text: 'hello',
      raw_xml: '<p>hello</p>',
      level: 2,
      original_text: 'hello',
      original_xml: '<p>hello</p>',
      edited: false,
      suggestion: null,
      pending_xml: null,
    },
    {
      block_id: 'b',
      kind: 'h2',
      text: 'world',
      raw_xml: '<h2>world</h2>',
      level: 0,
      original_text: 'world',
      original_xml: '<h2>world</h2>',
      edited: false,
      suggestion: null,
      pending_xml: null,
    },
  ]
}

describe('App block 处理器', () => {
  it('onSplitBlock 不可变地拆分当前块并插入本地新块', () => {
    const blocks = baseBlocks()
    const result = onSplitBlock(blocks, 'a', 2, 'he', 'llo', textToBlockXml)

    expect(result).not.toBe(blocks)
    expect(blocks[0].text).toBe('hello')
    expect(result).toHaveLength(3)
    expect(result[0]).toMatchObject({
      block_id: 'a',
      kind: 'p',
      text: 'he',
      pending_xml: '<p>he</p>',
      edited: true,
    })
    expect(result[1]).toMatchObject({
      kind: 'p',
      text: 'llo',
      raw_xml: '',
      level: 2,
      original_text: 'llo',
      original_xml: '',
      edited: true,
      suggestion: null,
      pending_xml: '<p>llo</p>',
    })
    expect(result[1].block_id).toMatch(/^local-/)
  })

  it('onMergeBlocks 合并前一块文本并移除当前块', () => {
    const blocks = baseBlocks()
    const result = onMergeBlocks(blocks, 'b', 'a', textToBlockXml)

    expect(result).not.toBe(blocks)
    expect(result).toHaveLength(1)
    expect(result[0]).toMatchObject({
      block_id: 'a',
      kind: 'p',
      text: 'helloworld',
      pending_xml: '<p>helloworld</p>',
      edited: true,
    })
    expect(blocks).toHaveLength(2)
    expect(blocks[0].text).toBe('hello')
  })

  it('onChangeBlockKind 更新 kind text pending_xml 和 edited', () => {
    const blocks = baseBlocks()
    const result = onChangeBlockKind(blocks, 'a', 'h1', '标题', textToBlockXml)

    expect(result).not.toBe(blocks)
    expect(result[0]).toMatchObject({
      block_id: 'a',
      kind: 'h1',
      text: '标题',
      pending_xml: '<h1>标题</h1>',
      edited: true,
    })
    expect(blocks[0].kind).toBe('p')
  })

  it('onBlocksChanged 批量更新文本并保持不可变', () => {
    const blocks = baseBlocks()
    const result = onBlocksChanged(
      blocks,
      [
        { block_id: 'a', text: '新正文' },
        { blockId: 'b', text: '新标题' },
      ],
      textToBlockXml,
    )

    expect(result).not.toBe(blocks)
    expect(result[0]).toMatchObject({
      text: '新正文',
      pending_xml: '<p>新正文</p>',
      edited: true,
    })
    expect(result[1]).toMatchObject({
      text: '新标题',
      pending_xml: '<h2>新标题</h2>',
      edited: true,
    })
    expect(blocks[0].text).toBe('hello')
    expect(blocks[1].text).toBe('world')
  })
})
