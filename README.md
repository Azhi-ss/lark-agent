# Lark Agent · 飞书文档 AI 编辑助手

基于 LLM 的飞书云文档编辑助手：加载飞书文档 → AI 提出修改建议 → 逐 block 审阅/编辑 → 写回飞书。提供「单文档编辑」与「方案构建」两种模式。

> Lark = 飞书（Feishu）国际版。

## 特性

- **单文档编辑**：左栏文档逐 block 可编辑（contenteditable），AI 的修改以「建议」形式合并到对应 block，支持逐条接受 / 拒绝 / 还原；写回用飞书 block-level `block_replace`（按 block-id 锚定，抗文本漂移），并带乐观锁防并发覆盖。
- **方案构建**：基于多份文档 + 多轮对话，流式产出结构化方案 Markdown。
- **文档搜索**：搜索飞书文档 / Wiki / 电子表格，一键导入编辑。
- **运行时配置**：LLM 接入（base_url / api_key / auth_token / model）与写回开关可在线修改，无需重启。

## 架构

```
┌──────────────┐      ┌──────────────────────────────────────┐
│  Vue 3 + Vite│ HTTP │  FastAPI                             │
│  (web/)      │─────▶│  ├─ /api/doc/load    fetch + blocks  │
│  Tailwind v4 │ SSE  │  ├─ /api/agent/chat  LLM 编辑建议流  │
│              │◀─────│  ├─ /api/doc/apply   block_replace   │
└──────────────┘      │  └─ /api/docs/search 文档搜索        │
                      └──────────┬───────────────────────────┘
                                 │ subprocess
                                 ▼
                      ┌────────────────────┐
                      │  lark-cli (v2 API) │──▶ 飞书云文档
                      └────────────────────┘
```

| 层 | 技术栈 | 目录 |
|---|---|---|
| 前端 | Vue 3 (`<script setup>`) + Vite + Tailwind v4 | `web/` |
| 后端 | FastAPI + Python 3.13 + Anthropic SDK | `backend/` |
| 飞书交互 | [lark-cli](https://www.npmjs.com/package/lark-cli)（v2 API，`--detail with-ids` 取 block-id） | `backend/lark/cli_wrapper.py` |
| 文档模型 | 飞书 docx XML 解析 + block 级 diff | `backend/lark/doc_xml.py` |

## 前置依赖

- Python ≥ 3.13（建议用 [uv](https://docs.astral.sh/uv/)）
- Node.js ≥ 18
- `lark-cli`：`npm i -g lark-cli`，首次使用前 `lark-cli auth login` 登录飞书账号

## 快速开始

```bash
# 1. 安装依赖
uv sync                          # 后端
cd web && npm install && cd ..   # 前端

# 2. 配置环境变量
cp .env.example .env             # 按需填写 LLM / 写回开关

# 3. 启动后端（http://127.0.0.1:8000）
uv run uvicorn backend.main:app --host 127.0.0.1 --port 8000

# 4. 启动前端（另一终端，http://localhost:5173）
cd web && npm run dev
```

浏览器打开 http://localhost:5173 ，粘贴飞书文档 URL（`/docx/` 或 `/wiki/`）即可加载编辑。

## 配置

环境变量见 `.env.example`，关键项：

| 变量 | 默认 | 说明 |
|---|---|---|
| `ANTHROPIC_API_KEY` | — | 真 Anthropic Claude 时填写 |
| `ANTHROPIC_BASE_URL` / `ANTHROPIC_AUTH_TOKEN` | — | 走代理（如火山 ARK）时填写 |
| `ANTHROPIC_MODEL` | `claude-sonnet-4-6` | 模型名 |
| `LARK_WRITEBACK` | `1` | `1` 允许写回飞书；`0` 仅模拟不真写 |
| `WEB_ORIGIN` | `http://localhost:5173` | 前端地址（CORS 白名单） |
| `LARK_CLI_PATH` | `lark-cli` | lark-cli 可执行路径 |

> LLM 接入也可在前端「设置」面板在线修改（运行时生效，不落 `.env`）。

## 单文档编辑工作流

```
加载文档 (fetch --detail with-ids)
  → 逐 block 渲染为 contenteditable
    → 用户手编  ── 或 ──  AI 处理 (replacements)
                              → pattern 定位到对应 block，挂为 suggestion
    → 接受 / 拒绝 / 还原
      → 写前 fetch 校验 revision_id（乐观锁）
        → block_replace 逐块写回飞书
```

### 已知限制

- 列表块（`ol`/`ul`）在 `fetch --detail with-ids` 下不返回 block-id，无法 `block_replace` 写回（渲染为只读）。
- 富文本块（`table`/`figure`/`img` 等）按只读占位处理，避免有损往返。
- 飞书 docx API 不支持原生 tracked changes / 修订模式，建议层为本应用自建。

## 测试

```bash
uv run pytest tests/ -q          # 后端单测 + 路由测试
cd web && npm run build          # 前端构建检查
```

## 项目结构

```
backend/
  api/routes.py        路由：load / chat / apply / search / settings
  agent/agent.py       LLM agent：edit_document / produce_solution 工具
  lark/cli_wrapper.py  lark-cli 封装：fetch_doc / update_doc / search_docs
  lark/doc_xml.py      docx XML 解析 + block 模型 + markdown 转换
  config.py            配置（frozen Settings + 运行时可变 LLM 配置）
web/
  src/App.vue          单文档/方案构建模式切换 + 状态管理
  src/components/      DocPane / AgentPane / AppFooter / WorkspaceView ...
docs/
  p1-editable-doc-plan.md   单文档可编辑 P1 设计文档
tests/                 pytest（doc_xml / routes / search / config）
```

## 安全

- `LARK_WRITEBACK=0` 可完全禁用写回，仅模拟。
- AI 生成内容在写回前必须人工审阅（前端底部有安全提示）。
- 写回带乐观锁：文档被他人改动后，写回会被拦截并提示重新加载，避免静默覆盖。

## License

MIT
