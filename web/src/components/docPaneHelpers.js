const EDITABLE_KINDS = new Set(['h1', 'h2', 'h3', 'h4', 'p', 'ul', 'ol', 'pre'])

export function isEditable(kind) {
  return EDITABLE_KINDS.has(kind)
}

export function tagFor(kind) {
  switch (kind) {
    case 'h1':
      return 'h1'
    case 'h2':
      return 'h2'
    case 'h3':
      return 'h3'
    case 'h4':
      return 'h4'
    case 'pre':
      return 'pre'
    default:
      return 'div'
  }
}

export function iconFor(kind) {
  return (
    {
      title: 'title',
      table: 'table_chart',
      figure: 'image',
      img: 'image',
      callout: 'campaign',
      grid: 'grid_on',
      bookmark: 'bookmark',
      cite: 'format_quote',
      hr: 'horizontal_rule',
    }[kind] || 'widgets'
  )
}

export function labelFor(kind) {
  return (
    {
      title: '文档标题',
      table: '表格',
      figure: '图片/附件',
      img: '图片',
      callout: '提示块',
      grid: '多维表格',
      bookmark: '书签',
      cite: '引用',
      hr: '分隔线',
    }[kind] || kind
  )
}

export function truncate(s, n) {
  if (!s) return ''
  return s.length > n ? s.slice(0, n) + '…' : s
}

export function matchMarkdownShortcut(text) {
  let match = text.match(/^(#{1,4})\s/)
  if (match) {
    return { kind: 'h' + match[1].length, cleaned: text.slice(match[0].length) }
  }

  match = text.match(/^-\s/)
  if (match) {
    return { kind: 'ul', cleaned: text.slice(match[0].length) }
  }

  match = text.match(/^(\d+)\.\s/)
  if (match) {
    return { kind: 'ol', cleaned: text.slice(match[0].length) }
  }

  return null
}
