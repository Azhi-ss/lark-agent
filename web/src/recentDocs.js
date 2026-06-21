// 最近访问文档缓存（localStorage 持久化）
//
// 记录用户加载过的飞书文档，去重、按最近访问时间倒序，上限 30 条。
// 用于「单文档编辑」空状态快捷入口与搜索浮层顶部，避免每次贴 URL 或重搜。
//
// 数据形态：{ url, title, openedAt }[]

const STORAGE_KEY = 'lark_agent.recent_docs'
const MAX_ITEMS = 30

function isBrowser() {
  return typeof window !== 'undefined' && typeof window.localStorage !== 'undefined'
}

function read() {
  if (!isBrowser()) return []
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    const arr = raw ? JSON.parse(raw) : []
    return Array.isArray(arr) ? arr : []
  } catch {
    return []
  }
}

function write(list) {
  if (!isBrowser()) return
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(list))
  } catch {
    // 配额满或隐私模式：静默放弃持久化，不影响功能
  }
}

/** 读取全部最近访问文档（按时间倒序）。 */
export function listRecent() {
  return read().slice().sort((a, b) => b.openedAt - a.openedAt)
}

/** 记录一次访问：去重并提到最前，超限截断。title 缺省时回退 url。 */
export function recordRecent(url, title = '') {
  if (!url) return
  const cleanTitle = (title || '').trim()
  const list = read().filter((d) => d.url !== url)
  list.unshift({
    url,
    title: cleanTitle || url,
    openedAt: Date.now(),
  })
  write(list.slice(0, MAX_ITEMS))
}

/** 移除一条最近访问记录。 */
export function removeRecent(url) {
  write(read().filter((d) => d.url !== url))
}

/** 清空全部最近访问。 */
export function clearRecent() {
  write([])
}
