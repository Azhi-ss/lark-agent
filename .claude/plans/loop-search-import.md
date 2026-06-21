# Loop Start: sequential · safe

Feature: 搜索导入飞书文档（Search-to-Import）

> 由模板填充。功能 1（LLM 设置增强）已完成,本轮聚焦搜索导入。
> 生成日期:2026-06-20。

## Objective

让用户除了粘贴飞书 URL,还能**搜索飞书文档**并批量导入到 Agent 上下文。覆盖单文档编辑模式与方案构建模式两种入口。

## Scope

- 后端新增 `GET /api/docs/search` 瘦身端点:转发 `lark-cli docs +search`,规整为 7 字段 + 分页透传;高亮标签 `<h>`/`<hb>`/`<b>` → `<mark>`,其余 HTML 转义(XSS 锁死)。
- 前端抽通用 `DocSearchPanel.vue`(搜索框 + 结果列表 + 分页 + 多选 + 导入按钮),回车/按钮才搜。
- 两处接入:方案构建模式左栏(导入→复用 `loadMany`);单文档编辑模式 TopBar 加搜索图标弹浮层(多选取第一份填 URL + 加载)。

## Non-goals

- 不做边输边搜(debounce 自动搜索)。
- 不做单文档模式的多文档切换(导入时只取第一份)。
- 不改 `loadMany` 本身(直接复用)。
- 不改功能 1(LLM 设置)已完成部分。
- 不引入新前端依赖。

## Acceptance Criteria

- `GET /api/docs/search?query=周报` 返回 `{results, has_more, page_token}`,每条含 `url, title, summary, owner, updated_at, doc_type, entity_type`;title/summary 仅含 `<mark>` 高亮,无其它原始 HTML 标签。
- 分页:传 `page_token` 能取下一页。
- 方案构建模式搜到文档可多选批量导入,导入后出现在上下文文档列表。
- 单文档模式搜索浮层导入后,TopBar URL 填入并自动加载。
- 后端搜索端点有测试(mock lark-cli 子进程),前端 build 通过。

## Quality Gates

- build pass (`cd web && npm run build`)
- lint pass (`uv run ruff check backend tests`)
- related tests pass (`uv run pytest -q`)
- security review pass(高亮 v-html 必须确保后端只输出 `<mark>`、其余转义;搜索 query 是用户输入,经 lark-cli 传递,需防注入)

## Stop Conditions

- 连续两轮同类失败
- 需求边界不清楚
- 需要引入新依赖但未确认
- 发现安全风险(尤其 v-html XSS)
- 超出 scope

---

## Next(执行序)

### 1. iterative-retrieval → Context Map

搜索功能涉及的现有代码:

| 模块 | 文件 | 角色 |
|---|---|---|
| lark 封装 | `backend/lark/cli_wrapper.py` | `_run()` 执行 lark-cli 并解析 JSON;`fetch_doc` 复用此模式。新增 `search_docs` 同模式调 `docs +search` |
| 路由 | `backend/api/routes.py` | `load_many`(批量加载,mock 友好);新增 `GET /docs/search` |
| 前端 API | `web/src/api.js` | 已预留 `searchDocs()`;`loadMany()` 可复用 |
| 前端组件 | `web/src/components/WorkspaceView.vue` | 方案构建左栏,已有 URL 添加 + loadMany 调用;接入 DocSearchPanel |
| 前端组件 | `web/src/components/TopBar.vue` | 单文档模式顶栏,加搜索图标;已有设置/帮助浮层范式可复用 |
| 前端组件 | `web/src/components/SettingsModal.vue`/`AboutModal.vue` | 浮层交互范式( Teleport + 遮罩 + 关闭) |

lark-cli 搜索实测返回结构:
```
data.results[]:
  - entity_type: "WIKI"|"DOC"
  - result_meta: {url, token, owner_name, update_time_iso, doc_types}
  - title_highlighted / summary_highlighted  (含 <h>/<hb>/<b>)
data.has_more, data.page_token
```

### 2. orch-add-feature planning

任务分解(=Step 3/4/5,延续 runbook):

| Task | 改动 | 依赖 |
|---|---|---|
| T1 后端搜索封装 | `cli_wrapper.search_docs(query, page_size, page_token)` 复用 `_run` | 无 |
| T2 后端搜索端点 | `routes`:GET `/docs/search`,瘦身 + 高亮转 mark + 转义 | T1 |
| T2.1 高亮安全函数 | `_to_safe_highlight(s)`:先 HTML 转义,再把 lark 标签转 `<mark>` | T2 |
| T3 搜索端点测试 | mock `_run`/subprocess,测瘦身字段 + 高亮白名单 + 分页 | T2 |
| T4 前端通用组件 | `DocSearchPanel.vue`:搜索框(回车/按钮)+ 结果列表(v-html 高亮)+ 多选 + 分页 + 导入 emit | T2 |
| T5 方案构建接入 | `WorkspaceView` 左栏嵌 DocSearchPanel,`@import` → loadMany | T4 |
| T6 单文档接入 | `TopBar` 加搜索图标 + 浮层,`@import` 取首份填 URL + onLoad | T4 |

### 3. Gate 1(停在此处,不写代码)

待确认项:
- [ ] 高亮白名单策略:确认采用"先全文 HTML 转义 → 再把 `<h>`/`<hb>`/`<b>` 还原为 `<mark>`"方案(而非保留 lark 原标签)。推荐此方案,XSS 面最小。
- [ ] 单文档模式多选取首份时,是否提示"单文档模式仅导入第一份"。推荐:提示。
- [ ] 搜索结果每页默认条数。推荐 15(lark-cli 默认,上限 20)。

**⏸ 停在 Gate 1,等待确认后进入实现。**
