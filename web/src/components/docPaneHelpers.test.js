import { describe, expect, it } from 'vitest'
import {
  iconFor,
  isEditable,
  labelFor,
  matchMarkdownShortcut,
  tagFor,
  truncate,
} from './docPaneHelpers.js'

describe('DocPane 纯函数', () => {
  it('tagFor 按块类型返回渲染标签', () => {
    expect(tagFor('h1')).toBe('h1')
    expect(tagFor('h2')).toBe('h2')
    expect(tagFor('h3')).toBe('h3')
    expect(tagFor('h4')).toBe('h4')
    expect(tagFor('pre')).toBe('pre')
    expect(tagFor('p')).toBe('div')
    expect(tagFor('ul')).toBe('div')
    expect(tagFor('ol')).toBe('div')
    expect(tagFor('unknown')).toBe('div')
  })

  it('isEditable 只允许正文类块编辑', () => {
    for (const kind of ['h1', 'h2', 'h3', 'h4', 'p', 'ul', 'ol', 'pre']) {
      expect(isEditable(kind)).toBe(true)
    }
    for (const kind of [
      'title',
      'table',
      'figure',
      'img',
      'callout',
      'grid',
      'bookmark',
      'cite',
      'hr',
    ]) {
      expect(isEditable(kind)).toBe(false)
    }
  })

  it('iconFor 和 labelFor 返回只读块展示映射与兜底', () => {
    expect(iconFor('title')).toBe('title')
    expect(iconFor('table')).toBe('table_chart')
    expect(iconFor('figure')).toBe('image')
    expect(iconFor('img')).toBe('image')
    expect(iconFor('callout')).toBe('campaign')
    expect(iconFor('grid')).toBe('grid_on')
    expect(iconFor('bookmark')).toBe('bookmark')
    expect(iconFor('cite')).toBe('format_quote')
    expect(iconFor('hr')).toBe('horizontal_rule')
    expect(iconFor('unknown')).toBe('widgets')

    expect(labelFor('title')).toBe('文档标题')
    expect(labelFor('table')).toBe('表格')
    expect(labelFor('figure')).toBe('图片/附件')
    expect(labelFor('img')).toBe('图片')
    expect(labelFor('callout')).toBe('提示块')
    expect(labelFor('grid')).toBe('多维表格')
    expect(labelFor('bookmark')).toBe('书签')
    expect(labelFor('cite')).toBe('引用')
    expect(labelFor('hr')).toBe('分隔线')
    expect(labelFor('unknown')).toBe('unknown')
  })

  it('truncate 处理空串和超长截断', () => {
    expect(truncate('', 3)).toBe('')
    expect(truncate(null, 3)).toBe('')
    expect(truncate('abc', 3)).toBe('abc')
    expect(truncate('abcd', 3)).toBe('abc…')
  })

  it('matchMarkdownShortcut 识别标题和列表快捷输入', () => {
    expect(matchMarkdownShortcut('# 标题')).toEqual({ kind: 'h1', cleaned: '标题' })
    expect(matchMarkdownShortcut('## 标题')).toEqual({ kind: 'h2', cleaned: '标题' })
    expect(matchMarkdownShortcut('### x')).toEqual({ kind: 'h3', cleaned: 'x' })
    expect(matchMarkdownShortcut('#### x')).toEqual({ kind: 'h4', cleaned: 'x' })
    expect(matchMarkdownShortcut('- 项')).toEqual({ kind: 'ul', cleaned: '项' })
    expect(matchMarkdownShortcut('1. 项')).toEqual({ kind: 'ol', cleaned: '项' })
    expect(matchMarkdownShortcut('普通文本')).toBeNull()
    expect(matchMarkdownShortcut('#无空格')).toBeNull()
  })
})
