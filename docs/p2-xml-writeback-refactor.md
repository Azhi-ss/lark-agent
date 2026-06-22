# P2 重构计划：对齐飞书原生 XML block 模型 + 写回后刷新

> 状态：待实施 | 解决 P1 遗留的两个 bug + 根本性对齐飞书格式
> 范围：仅「单文档编辑」模式写回链路重构

## 1. 问题与根因（已联调坐实）

### Bug 1：连续修改后「文档已被修改请重新加载」
- **根因**：`block_replace` 后 **block-id 必变**（飞书硬约束，XML/markdown 模式皆然）。
  实测：`doxcnPzT4sWMaGHqOdhUPbfrtTd` → `doxcnYD0dFPbBrN1VljYltvj0tg`。
- 前端写回成功后只更新 revision_id，没刷新 block-id。下次写回用失效旧 block-id →
  静默不写/部分失败 → revision 失准 → 写前 fetch 校验 conflict。

### Bug 2：删除内容写回失败
- 后端 block_delete 本身正确。根因在前端 contenteditable 删空后 innerText 非纯空串，
  且语义不清（删整块 vs 清空保留段落，飞书无空段落概念）。

### 深层问题：markdown 写回是双格式有损往返
- fetch 同时取 XML（解析 block-id）+ markdown（agent 上下文 + 写回），两份不一致。
- 飞书原生格式是 XML，markdown 写回需飞书再解析回 block，是便捷通道非推荐路径。

## 2. 最优方案

**两根支柱：**
1. **XML 作为单一真相源**：fetch 用 XML（带 id），block 模型保留原始 XML，写回用 XML content。
2. **写回后重新 fetch**：刷新 block-id + revision_id，根治漂移（不可绕过的飞书约束）。

## 3. 数据契约（前后端定死）

### 3.1 Block 模型（后端）

```python
@dataclass(frozen=True)
class Block:
    kind: str          # title / h1-h4 / p / ul / ol / pre / table / figure / img / ...
    text: str          # 纯文本（递归抽取，给 agent 看）
    level: int         # 标题级别
    raw_xml: str       # 原始 XML 片段（含 id 属性）
    block_id: str      # 从 raw_xml 提取的 id，无则 ""
    meta: dict         # 其他属性
```

### 3.2 `/doc/load` 响应

```jsonc
{
  "document_id": "doxcnXXX",
  "revision_id": 12,
  "blocks": [
    {
      "block_id": "blkcnA",
      "kind": "p",
      "text": "纯文本",
      "raw_xml": "<p id=\"blkcnA\">纯文本</p>",
      "level": 0
    }
  ]
}
```
- 不再返回 `markdown` 整篇（agent 上下文改用 `blocks_to_text`）。
- 每块带 `raw_xml`（含 id）+ `text`（纯文本，agent 看 + 前端编辑初始值）。

### 3.3 `/agent/chat` done 事件
agent 仍产出 `pattern→content`。pattern 必须落在单块 text 内（system prompt 约束）。
done 事件 `{replacements, final_text}` 不变。

### 3.4 `/doc/apply` 请求（XML 写回）

```jsonc
{
  "url": "...",
  "revision_id": 12,
  "edits": [
    { "block_id": "blkcnA", "xml": "<p>新内容</p>" }
  ]
}
```
- `xml` 为该块编辑后的完整 XML 片段（前端按 kind 生成）。
- 空 xml（`""`）= 删除整块 → block_delete。
- 响应：
```jsonc
{
  "ok": true,
  "mode": "block_replace",
  "final_revision_id": 13,
  "conflict": false,
  "count": 2,
  "results": [{ "block_id": "blkcnA", "ok": true }]
}
```
- 写前 fetch 校验 revision_id（乐观锁，保持 P1 逻辑）。
- **写回成功后前端必须重新 load**（block-id 已变）。

## 4. 文件改动清单

### 后端

| 文件 | 改动 |
|---|---|
| `backend/lark/doc_xml.py` | `_meta_of` 已含 id（P1）；新增 `block_id_of(block)` 提取 id；`block_to_text` 已有；`blocks_to_blocklist(content_xml)` 改为返回 `{block_id, kind, text, raw_xml, level}`（raw_xml 取自 block.raw_xml，block_id 取自 meta['id']）；保留 `blocks_to_text`（agent 上下文） |
| `backend/lark/cli_wrapper.py` | `fetch_doc` 已支持 `detail="with-ids"`（P1）。无改动 |
| `backend/api/routes.py` | `load_doc`：只 fetch XML（with-ids），返回 blocks（含 raw_xml）；不再 fetch markdown；agent 上下文用 `blocks_to_text(blocks)`。`ApplyRequest.edits` 改 `BlockEdit{block_id, xml}`。`_apply_block_edits`：空 xml→block_delete；否则 block_replace `--doc-format xml --content <xml>`。乐观锁校验保留 |
| `backend/agent/agent.py` | `SYSTEM_PROMPT`：pattern 必须落在单块纯文本内、连续逐字。`run_agent_stream` user_msg 用 `blocks_to_text` 而非整篇 markdown |

### 前端

| 文件 | 改动 |
|---|---|
| `web/src/api.js` | `loadDoc` 透传 blocks（含 raw_xml）；`applyEdits(url, edits, revisionId)` body `{url, revision_id, edits:[{block_id, xml}]}` |
| `web/src/App.vue` | block 结构改 `{block_id, kind, text, raw_xml, level, edited, suggestion}`；onLoad map（edited:false, suggestion:null），text 作编辑初始值；editBlock 收新文本→生成该块 xml→存 `pending_xml`+edited；onApply 收集 edited 块的 xml→applyEdits；**写回成功后调 onLoad() 重新加载**（刷新 block-id/revision）；删除块（空文本）→xml=""→block_delete |
| `web/src/components/DocPane.vue` | contenteditable 编辑纯文本；blur→emit('edit-block', block_id, text)（纯文本非 markdown）；helper `textToBlockXml(kind, text)` 按 kind 包标签：title/h1→`<h1>text</h1>`...p→`<p>text</p>`；ul→`<ul><li>...</li></ul>`；ol 同；pre→`<pre lang=""><code>text</code></pre>`；删空→空 xml |
| `web/src/components/AgentPane.vue` | 不变（建议摘要 + 定位） |

### 测试

| 文件 | 改动 |
|---|---|
| `tests/test_doc_xml.py` | blocks_to_blocklist 返回含 raw_xml/block_id；block_id_of |
| `tests/test_routes.py` | /doc/load 返回 blocks 含 raw_xml；/doc/apply edits 走 xml block_replace（doc_format=xml）；空 xml→block_delete；乐观锁冲突 |

## 5. 关键实现细节

### 5.1 纯文本 → block XML（前端 DocPane）

```js
function textToBlockXml(kind, text) {
  const esc = (s) => s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
  const t = esc(text)
  switch (kind) {
    case 'title': return `<h1>${t}</h1>`   // title 块写回用 h1? 见下注
    case 'h1': return `<h1>${t}</h1>`
    case 'h2': return `<h2>${t}</h2>`
    case 'h3': return `<h3>${t}</h3>`
    case 'h4': return `<h4>${t}</h4>`
    case 'ul': return `<ul>${t.split('\n').map(l=>l.trim()?`<li>${esc(l)}</li>`:'').join('')}</ul>`
    case 'ol': return `<ol>${t.split('\n').map(l=>l.trim()?`<li>${esc(l)}</li>`:'').join('')}</ol>`
    case 'pre': return `<pre><code>${t}</code></pre>`
    default: return `<p>${t}</p>`
  }
}
```
> 注：title 块（文档标题）的 block_replace 行为需实测——飞书 title 可能不可 block_replace。
> P2 范围：title 块标只读不可编辑（与 table/figure 同），避免踩坑。

### 5.2 写回后重新加载（核心修复）

```js
async function onApply() {
  const edited = blocks.value.filter(b => b.edited)
  if (!edited.length || applying.value) return
  applying.value = true
  try {
    const edits = edited.map(b => ({ block_id: b.block_id, xml: b.pending_xml ?? b.raw_xml }))
    const res = await applyEdits(docUrl.value, edits, docMeta.value.revision_id)
    if (res.conflict) {
      applyStatus.value = '文档已被修改，请重新加载'
    } else if (res.ok) {
      applyStatus.value = `已写回飞书（${res.count} 块），正在刷新…`
      await onLoad()  // 关键：重 fetch 刷新 block-id + revision_id
      applyStatus.value = `已写回飞书（${res.count} 块）`
    } else {
      applyStatus.value = `部分失败：${res.results.filter(r=>!r.ok).length} 块`
    }
  } catch (e) {
    applyStatus.value = '写回失败: ' + e.message
  } finally {
    applying.value = false
  }
}
```

### 5.3 可编辑块范围（P2 收紧）
仅 `h1-h4 / p / ul / ol / pre` 可编辑。`title` 改只读（block_replace 行为不确定）。
`table/figure/img/callout/grid/bookmark/cite/hr` 只读占位。

### 5.4 删除语义
用户删空某块文本 → `pending_xml = ""` → 写回走 block_delete → 重 load 后该块从列表消失。
语义清晰：删空 = 删整块（飞书无空段落）。

## 6. 风险与缓解

| 风险 | 缓解 |
|---|---|
| title 块 block_replace 不确定 | P2 标 title 只读 |
| 富文本块（加粗/链接）丢失 | P2 仅纯文本编辑，富文本块只读（同 P1） |
| 重 load 闪烁 | onLoad 保留 docUrl，仅刷新 blocks/revision；可加 loading 态 |
| agent pattern 定位 | pattern 落单块 text 内，前端用 text 子串匹配定位 block_id |

## 7. 验收标准

- [ ] 连续修改多块 + 写回，无「文档已被修改」冲突（重 load 刷新 block-id）。
- [ ] 删空块 + 写回，该块从文档消失（block_delete），无失败。
- [ ] 写回用 XML 格式（doc_format=xml），对齐飞书原生。
- [ ] 写回成功后自动重新加载，block-id/revision_id 最新。
- [ ] 乐观锁冲突仍正确拦截。
- [ ] ruff + pytest + 前端 build 通过；方案构建模式不受影响。
