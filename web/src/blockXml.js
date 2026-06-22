// 纯文本 → 飞书 block XML 片段（P2 XML 写回单一真相源）。
// 见 docs/p2-xml-writeback-refactor.md §3.4 / §5.1
// 不引入依赖，纯函数无副作用。

/** 转义 XML 文本节点的 & < > */
export const escapeXml = (s) =>
  String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

/**
 * 按块 kind 把纯文本包成飞书 block XML 片段（写回用，不含 id 属性）。
 * - 空文本一律返回 ""（语义：删整块 → 后端 block_delete，见 §5.4）。
 * - ul/ol：按行拆分，空行跳过，每行一个 <li>。
 * - title 块标只读不应走到这里；若误调按 h1 兜底（与 §5.1 注一致）。
 * @param {string} kind block kind（h1-h4 / p / ul / ol / pre ...）
 * @param {string} text 纯文本
 * @returns {string} XML 片段；空文本返回 ""
 */
export function textToBlockXml(kind, text) {
  if (text == null) text = ''
  if (text === '') return ''
  const t = escapeXml(text)
  switch (kind) {
    case 'title':
    case 'h1':
      return `<h1>${t}</h1>`
    case 'h2':
      return `<h2>${t}</h2>`
    case 'h3':
      return `<h3>${t}</h3>`
    case 'h4':
      return `<h4>${t}</h4>`
    case 'ul':
      return (
        '<ul>' +
        text
          .split('\n')
          .map((l) => (l.trim() ? `<li>${escapeXml(l)}</li>` : ''))
          .join('') +
        '</ul>'
      )
    case 'ol':
      return (
        '<ol>' +
        text
          .split('\n')
          .map((l) => (l.trim() ? `<li>${escapeXml(l)}</li>` : ''))
          .join('') +
        '</ol>'
      )
    case 'pre':
      return `<pre><code>${t}</code></pre>`
    default:
      return `<p>${t}</p>`
  }
}
