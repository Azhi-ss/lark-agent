# P1 实施计划：单文档可编辑 + AI 建议合并 + block-level 写回

> 状态：待实施 | 来源：council 决议 + lark-cli 能力边界核查
> 范围：仅「单文档编辑」模式（editor），不动「方案构建」模式（workspace）

## 1. 背景与决策

### 现状（问题）
- 左栏 `DocPane` 用 `v-html` 渲染 markdown 字符串，**只读**，用户无法编辑。
- AI 产出 `replacements[{pattern, content, reason}]`，渲染为右栏 diff 卡片。
- 用户只能「拒绝」（移除卡片），「保留」是**空操作**（`App.vue:122`）。
- 写回 `/doc/apply` 用 `str_replace` + `revision_id=-1`（`routes.py:144`）：文本漂移即错位，且无并发保护。

### lark-cli 能力边界（已核查）
- `docs +update` 支持 8 种 command：`str_replace / block_insert_after / block_replace / block_delete / block_copy_insert_after / block_move_after / overwrite / append`。
- `block_replace --block-id <id> --content <md> --doc-format markdown` 可行：按 block-id 锚定替换，**不受文本漂移影响**；markdown 内容不带样式但可写入。
- `docs +fetch --detail with-ids` 返回 `<p id="blkcnXXX">` 形式，block-id 可用于定位。
- `--revision-id` 可指定基准版本做乐观锁；fetch 已返回 `revision_id`。
- **不支持**飞书原生 tracked changes / 修订模式（评论走另一个 skill）——故 suggestion 层必须自建。

### council 决议（已采纳）
- 否决 TipTap 富文本：引入 markdown↔ProseMirror↔docx 双倍有损往返，过度工程。
- 否决纯 markdown textarea overwrite：丢 block-id 映射 + `overwrite` 有损（丢图片/评论）。
- 否决飞书原生修订：API 不支持。
- **采纳**：左栏逐 block 可编辑（contenteditable）+ block-id 绑定 + AI 建议合并到对应 block + block-level 写回 + revision 乐观锁。

## 2. 目标与非目标

### 目标
1. 左栏文档**逐 block 可编辑**（用户能直接改任意 block 文本）。
2. AI 的修改以**建议**形式合并到左栏对应 block（旁显预览 + 接受/拒绝），而非右栏独立 diff 卡片。
3. 用户接受建议或手编后，**逐 block 用 `block_replace` 写回飞书**，抗文本漂移。
4. 写回用加载时的 `revision_id` 做**乐观锁**，版本冲突则拒写并提示重新加载。
5. 保留原文快照，支持「还原该 block」。

### 非目标（P1 不做）
- 富文本格式编辑（加粗/颜色/表格编辑）——P1 仅纯文本/段落级编辑。
- 多人实时协作感知。
- 写回后撤销（飞书侧）。
- 方案构建模式（workspace）任何改动。

## 3. 数据契约（前后端定死）

### 3.1 Block 模型

`fetch --detail with-ids` 解析后，每个 block：

```ts
interface Block {
  block_id: string          // 飞书 block-id（blkcnXXX）；title 等无 id 的为 ""
  kind: string              // title / h1..h4 / p / ul / ol / pre / table / figure / img / hr ...
  text: string              // 纯文本（递归抽取，给 agent 看）
  markdown: string          // 该 block 的 markdown 表示（前端编辑/写回用）
  original: string          // 加载时的原始 markdown（判断是否被编辑）
  level: number             // 标题级别，非标题 0
}
```

### 3.2 `/doc/load` 响应（向后兼容增量）

```jsonc
{
  "document_id": "doxcnXXX",
  "revision_id": 12,
  "markdown": "整篇 markdown（agent 上下文，保留）",
  "block_count": 18,
  "blocks": [                // 新增
    { "block_id": "blkcnA", "kind": "title", "text": "周报", "markdown": "# 周报", "original": "# 周报", "level": 0 },
    { "block_id": "blkcnB", "kind": "p", "text": "本周...", "markdown": "本周...", "original": "本周...", "level": 0 }
  ]
}
```

### 3.3 `/agent/chat` done 事件（不变 + 保留原始 replacements）

agent 仍产出 `pattern→content`。done 事件保持 `{replacements, final_text}`。
**pattern→block_id 的定位放前端**（前端已有 blocks）。

### 3.4 `/doc/apply` 请求（新签名，向后兼容旧字段）

```jsonc
{
  "url": "https://...",
  "revision_id": 12,                 // 加载时版本，做乐观锁
  "edits": [                          // 新：block-level
    { "block_id": "blkcnB", "content": "改后的 markdown" }
  ],
  "replacements": [...]               // 旧：存在则降级 str_replace（兼容）
}
```

响应：

```jsonc
{
  "ok": true,
  "mode": "block_replace",
  "final_revision_id": 13,
  "conflict": false,
  "count": 2,
  "results": [
    { "block_id": "blkcnB", "ok": true, "new_revision_id": 13 },
    { "block_id": "blkcnC", "ok": false, "error": "..." }
  ]
}
```

冲突（`revision_id` 不匹配）时：`ok=false, conflict=true`，前端提示「文档已被他人修改，请重新加载」。

## 4. 文件改动清单

### 后端

| 文件 | 改动 |
|---|---|
| `backend/lark/cli_wrapper.py` | `fetch_doc` 新增 `detail` 参数（默认 `simple`，传 `with-ids` 时 XML 带 id 属性）；`update_doc` 已支持 `block_id`，无需大改，确认 `revision_id` 透传 |
| `backend/lark/doc_xml.py` | `_meta_of` 的 keep 集合加 `"id"`；新增 `block_to_markdown(block) -> str`（把单个 Block 转 markdown 片段）；新增 `blocks_to_blocklist(xml) -> list[dict]` 产出前端 Block 列表 |
| `backend/api/routes.py` | `load_doc`：xml fetch 传 `detail="with-ids"`，返回 `blocks`；`apply_edits`：优先 `edits` 走 `block_replace` 串行 + 乐观锁，`replacements` 走旧 str_replace 兼容 |
| `backend/agent/agent.py` | `SYSTEM_PROMPT` 加约束：pattern 必须落在**单个 block 的 markdown 内**、连续逐字、不用省略号语法（便于前端定位） |

### 前端

| 文件 | 改动 |
|---|---|
| `web/src/api.js` | `loadDoc` 透传 `blocks`；`applyEdits(url, edits, revisionId)` 新签名（旧调用点同步改） |
| `web/src/App.vue` | 新增 `blocks` 状态；`onLoad` 存 blocks；`onChat` done 后用 pattern 在 blocks 内子串匹配定位 → 给 block 挂 `suggestion`；`onApply` 收集 edited blocks 调新 `applyEdits`；新增 `acceptSuggestion/rejectSuggestion/editBlock/resetBlock` |
| `web/src/components/DocPane.vue` | v-html 只读 → 逐 block 渲染可编辑区（contenteditable p/h/li；pre 用 textarea）；block 有 pending suggestion 时旁显「建议预览 + 接受/拒绝」；edited block 显「还原」 |
| `web/src/components/AgentPane.vue` | diff 卡片列表 → 建议摘要列表（点击定位/滚动到左栏对应 block） |
| `web/src/components/AppFooter.vue` | 按钮计数改为「待写回 block 数」；文案微调 |

### 测试

| 文件 | 改动 |
|---|---|
| `tests/test_doc_xml.py` | with-ids 解析（id 进 meta）、`block_to_markdown` 各 kind、`blocks_to_blocklist` |
| `tests/test_routes.py` | `/doc/load` 返回 blocks；`/doc/apply` block_replace 路径 + 乐观锁冲突；旧 replacements 兼容路径 |

## 5. 关键实现细节

### 5.1 pattern → block_id 定位（前端，App.vue）

agent 受约束后 pattern 是单 block 内连续文本。前端对每个 replacement：

```js
function locateBlock(pattern) {
  // 1. 精确子串匹配某 block.markdown
  for (const b of blocks.value) {
    if (b.markdown.includes(pattern)) return b.block_id
  }
  // 2. 归一化（去空白）后再匹配
  const norm = (s) => s.replace(/\s+/g, '')
  for (const b of blocks.value) {
    if (norm(b.markdown).includes(norm(pattern))) return b.block_id
  }
  return null // 无法定位 → 前端标记 unlocated，提示用户手动
}
```

定位成功 → 给该 block 挂 `suggestion = {content, reason, state:'pending'}`。
失败 → 进入「未定位建议」列表，用户可手动复制 content 贴到任意 block。

### 5.2 接受/拒绝/手编语义

- **接受建议**：`block.markdown = suggestion.content`；`block.edited = true`；`suggestion.state = 'accepted'`。
- **拒绝建议**：`suggestion.state = 'rejected'`；block 不变。
- **手编**：用户改 block.markdown → `block.edited = true`。
- **还原**：`block.markdown = block.original`；`block.edited = false`；清除 suggestion。

`onApply` 收集所有 `edited === true` 的 block → `edits`。

### 5.3 block_replace 串行 + 乐观锁（routes.py）

```python
def apply_edits(req):
    if req.edits:
        cur_rev = req.revision_id
        results = []
        for e in req.edits:
            data = update_doc(url, command="block_replace",
                              block_id=e.block_id, content=e.content,
                              doc_format="markdown", revision_id=cur_rev)
            new_rev = data.get("document", {}).get("revision_id", cur_rev)
            # 若服务端报版本冲突 → 标记 conflict，中断后续
            results.append({...})
            cur_rev = new_rev
        return {"ok": all(...), "mode": "block_replace",
                "final_revision_id": cur_rev, "conflict": ..., "results": results}
    # 旧路径兼容
    ...
```

> 注：`block_replace` 后该 block-id 不保证继续可用（文档原话），但**不同 block-id 之间互不影响**，串行替换不同 block 仍安全。若同一 block 被编辑两次（不应发生，前端去重），需合并。

### 5.4 block → markdown 转换（doc_xml.py）

复用 `blocks_to_text` 思路但输出 markdown 语法：
- title → `# text`；h1..h4 → `#`~`####` text
- p → text
- ul → `- li\n- li`；ol → `1. li`
- pre → ```` ```\ncode\n``` ````
- table → markdown 表格（首行表头 + 分隔行）
- figure/img → `![alt](url)` 或 `[图片]`（只读，不可编辑——P1 标记为不可编辑块）
- hr → `---`

### 5.5 可编辑块的范围限制（P1）

为控制复杂度，**仅以下 kind 可编辑**：`title / h1..h4 / p / ul / ol / pre`。
`table / figure / img / callout / grid / bookmark / cite` 渲染为**只读占位**（显示但不可编辑，不参与写回）。

## 6. 风险与缓解

| 风险 | 缓解 |
|---|---|
| pattern 跨 block / 匹配不到 | system prompt 约束单块；前端归一化兜底；失败降级「未定位建议」手动应用 |
| `block_replace` 后 block-id 失效影响后续 | 串行且只替换不同 block；前端去重同一 block 的多次编辑 |
| 乐观锁误判（revision 语义） | 冲突时明确提示重新加载，不静默覆盖；写回前可重新 fetch 校验 |
| 富文本块（表格/图片）编辑 | P1 标记只读，不参与写回，避免有损往返 |
| 向后兼容 | `/doc/apply` 保留 `replacements` 旧路径；前端其他调用点同步改签名 |

## 7. 验收标准

- [ ] 加载文档后，左栏每个文本 block 可点击编辑、改完标记 edited。
- [ ] AI 处理后，建议出现在左栏对应 block 旁，可接受/拒绝；接受后内容并入 block。
- [ ] 未定位的建议有明确提示，不静默丢失。
- [ ] 「确认写回」按 block-level 写回飞书（`LARK_WRITEBACK=0` 时模拟成功）。
- [ ] 版本冲突时拒写并提示重新加载，不静默覆盖。
- [ ] 旧的 str_replace 路径仍可用（兼容）。
- [ ] `tests/test_doc_xml.py`、`tests/test_routes.py` 新增用例通过；`ruff check` 无新增告警。
- [ ] 方案构建模式不受影响。

## 8. Team 分工（实施阶段）

- **后端 agent**：cli_wrapper + doc_xml + routes + agent prompt（强耦合，一人完成）。
- **前端 agent**：api.js + App.vue + DocPane.vue + AgentPane.vue + AppFooter.vue（基于 §3 契约，可与后端并行）。
- **测试 agent**：tests/test_doc_xml.py + tests/test_routes.py（后端完成后）。
- **集成验证**：ruff + pytest + 前端 build + 手动联调（主循环）。
