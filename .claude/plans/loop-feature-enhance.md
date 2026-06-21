# Loop Runbook: 功能增强 · sequential · safe

> 由 `/grill-me` 拷问后生成。目标:为飞书周报 Agent 增强两个功能——
> ① LLM 设置显示/隐藏 key + 延迟/健康度检测;② 搜索导入飞书文档。
> 生成日期:2026-06-20。

## 1. 元信息

| 项 | 值 |
|---|---|
| 模式 | `sequential`(顺序迭代,每轮聚焦一个 Step) |
| 安全档 | `safe`(每步 ruff + pytest + 前端 build 验证门) |
| 停止条件 | 连续 3 轮无进展(no-progress=3)或 Step 全完成 |
| 硬上限 | 最多 12 轮 |

## 2. 决策记录(10 轮拷问结论)

### 功能 1:LLM 设置增强

- **D1** 用 loop 模式实现(非新建命令)。
- **D2** GET `/api/settings/llm` **直接回明文 key**,前端密码框默认遮罩、点眼睛切换显示。
- **D3** 检测:打开面板自动测一次 + 手动"测试连接"可重测。
- **D4** 检测发**真实推理请求**(`messages.create` max_tokens=1),失败按错误类型分类。
- **D5** 延迟分级着色:绿 <1000ms / 黄 1000–3000ms / 红 >3000ms。
- **D6** 同步端点 `POST /api/settings/llm/test`,阻塞返回(后端 client 10s timeout)。
- **D7** 检测**面板当前输入的临时配置**(端点接收 base_url/api_key/auth_token/model,临时构造 client,**不落库**)。
- **D8** 错误分类五类:`network` / `auth` / `model` / `rate_limit` / `unknown`(兜底保留原始信息)。

### 功能 2:搜索导入

- **D9** 两种模式都能搜索,各自导入(单文档编辑 + 方案构建)。
- **D10** 多选批量导入,点"导入"立即 fetch markdown(复用现有 `loadMany`)。
- **D11** `GET /api/docs/search?query=&page_size=&page_token=`,后端规整为 `{results, has_more, page_token}`。
- **D12** 后端瘦身:只返回 `url, title, summary, owner, updated_at, doc_type, entity_type`。
- **D13** 高亮:lark 的 `<h>`/`<hb>`/`<b>` → `<mark>`,**其余 HTML 转义**,前端 v-html 渲染(严格白名单,锁死 XSS)。
- **D14** 单文档编辑模式:TopBar 加搜索图标 → 弹搜索浮层;多选导入时**取第一份**填 URL 并加载。
- **D15** 抽通用 `DocSearchPanel` 组件,两处复用,落点靠 `@import="onImport(urls)"` 回调参数化。
- **D16** 回车/按钮才搜(不边输边搜,避免半截查询 + 分页 token 复杂化)。

### 搜索 API 实测结构(lark-cli docs +search)

返回 `data.results[]`,关键字段:
- `result_meta.{url, token, owner_name, update_time_iso, doc_types}`
- `title_highlighted` / `summary_highlighted`(含 `<h>`/`<hb>`/`<b>` 高亮标签)
- `data.has_more`、`data.page_token`(分页,下次请求回传)

## 3. Step 清单(按优先级)

| # | Step | 验收 | 完成标志 |
|---|---|---|---|
| 1 | 后端:`GET /api/settings/llm` 改回明文 key;新增 `POST /api/settings/llm/test` 同步检测端点(临时配置不落库,五类错误分类,延迟分级) | ruff + pytest(含新端点测试)通过 | ✅ |
| 2 | 前端:SettingsModal 加 key 显示/隐藏切换(眼睛图标);加"测试连接"按钮 + 打开自动测一次;延迟分级着色 + 错误类型展示 | npm run build 通过 | ✅ |
| 3 | 后端:新增 `GET /api/docs/search` 瘦身端点(7 字段 + 高亮转 mark + 转义),分页透传 | ruff + pytest(含搜索端点测试,mock lark-cli)通过 | ✅ |
| 4 | 前端:抽通用 `DocSearchPanel.vue`(搜索框+结果列表+分页+多选+导入);回车/按钮搜 | build 通过 | ✅ |
| 5 | 前端:方案构建模式左栏接入 DocSearchPanel,@import → loadMany;单文档模式 TopBar 加搜索图标弹浮层,@import 取第一份填 URL+加载 | build 通过 | ✅ |
| 6 | 端到端验证:后端启动 + health;前端 build;手测搜索/检测路径(需 lark-cli + LLM 凭证,凭证缺失时记为跳过) | 启动 OK,build OK | ✅ |

## 4. safe 模式约束

- 每步最小必要改动,不重构无关代码。
- 不删除/覆盖用户未要求的内容。
- 每步验证门:`uv run ruff check backend tests && uv run pytest -q && (cd web && npm run build)`。
- git commit 仅在 Step 完成后(safe checkpoint)。
- v-html 渲染高亮必须确保后端只输出 `<mark>`,其余转义(XSS 锁死)。

## 5. 启动与监控

```bash
export ECC_HOOK_PROFILE=safe
# /loop 读取 .claude/plans/loop-feature-enhance.md 按 Step 1→6 推进,每步跑验证门,no-progress>=3 停
# /ecc:loop-status
```
