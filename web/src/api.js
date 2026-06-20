// 后端 API 封装

const BASE = '/api'

export async function loadDoc(url) {
  const res = await fetch(`${BASE}/doc/load`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `加载失败 (${res.status})`)
  }
  return res.json()
}

export async function health() {
  const res = await fetch(`${BASE}/health`)
  return res.json()
}

/**
 * 流式调用 agent，通过 SSE 接收事件。
 * @param {string} markdown
 * @param {string} instruction
 * @param {(ev: {type: string, data: any}) => void} onEvent
 */
export async function chatAgent(markdown, instruction, onEvent) {
  const res = await fetch(`${BASE}/agent/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ markdown, instruction }),
  })
  if (!res.ok || !res.body) {
    throw new Error(`agent 调用失败 (${res.status})`)
  }
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        try {
          onEvent(JSON.parse(line.slice(6)))
        } catch {
          // 忽略解析失败的行
        }
      }
    }
  }
}

export async function applyEdits(url, replacements) {
  const res = await fetch(`${BASE}/doc/apply`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ url, replacements, revision_id: -1 }),
  })
  return res.json()
}

// ===== Phase 3: 方案构建模式 =====

export async function loadMany(urls) {
  const res = await fetch(`${BASE}/doc/load_many`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ urls }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `批量加载失败 (${res.status})`)
  }
  return res.json()
}

/**
 * 流式调用方案构建 agent。
 * @param {Array<{url:string,markdown:string}>} docs
 * @param {Array<{role:string,content:string}>} messages
 * @param {(ev: {type:string,data:any}) => void} onEvent
 */
export async function chatSolution(docs, messages, onEvent) {
  const res = await fetch(`${BASE}/agent/solution`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ docs, messages }),
  })
  if (!res.ok || !res.body) {
    throw new Error(`agent 调用失败 (${res.status})`)
  }
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        try {
          onEvent(JSON.parse(line.slice(6)))
        } catch {
          // ignore
        }
      }
    }
  }
}

/** 浏览器端导出 markdown 为 .md 文件下载（不走后端，纯 Blob）。 */
export function exportMd(markdown, filename = 'solution.md') {
  const safeName = filename.toLowerCase().endsWith('.md') ? filename : `${filename}.md`
  const blob = new Blob([markdown], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = safeName
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export async function saveWorkspace({ sessionId = null, name, docUrls, messages, solutionMarkdown = '' }) {
  const res = await fetch(`${BASE}/workspace/save`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id: sessionId,
      name,
      doc_urls: docUrls,
      messages,
      solution_markdown: solutionMarkdown,
    }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `保存失败 (${res.status})`)
  }
  return res.json()
}

export async function listWorkspaces() {
  const res = await fetch(`${BASE}/workspace/list`)
  if (!res.ok) throw new Error(`列出会话失败 (${res.status})`)
  return res.json()
}

export async function loadWorkspace(sessionId) {
  const res = await fetch(`${BASE}/workspace/${encodeURIComponent(sessionId)}`)
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err.detail || `加载会话失败 (${res.status})`)
  }
  return res.json()
}
