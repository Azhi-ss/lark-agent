# 飞书周报 Agent

通过可视化 Web 界面，用 AI agent 提炼和修改飞书周报文档，确认 diff 后写回飞书。

## 能力

- 加载飞书周报文档（docx / wiki URL）
- agent 提炼要点 / 按自然语言指令修改周报
- 界面展示每处修改的 diff（原文 → 替换为）
- 确认后一键写回飞书（基于 `lark-cli docs +update str_replace`）

## 架构

```
Vue3 + Vite (5173)  ──/api──►  FastAPI (8000)
                                  ├─ agent: anthropic SDK（火山代理 / glm-5.2）
                                  └─ lark: lark-cli 子进程封装（docs +fetch/+update）
```

## 前置条件

1. `lark-cli` 已安装并 `lark-cli auth login` 完成（user 身份）
2. LLM 接入（二选一）：
   - 真 Anthropic：设置 `ANTHROPIC_API_KEY`
   - 火山代理：环境已注入 `ANTHROPIC_BASE_URL` + `ANTHROPIC_AUTH_TOKEN`（默认）

## 启动

```bash
# 后端
uv sync
uv run uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload

# 前端（另开终端）
cd web
npm install
npm run dev
```

打开 http://localhost:5173 ，粘贴飞书周报 URL → 加载 → 输入指令 → 让 Agent 处理 → 确认 diff → 写回飞书。

## 关键设计

- **markdown str_replace**：agent 看文档真实 markdown，产出 `pattern→content` 替换；apply 用 `--doc-format markdown` 跨行匹配，`revision_id=-1` 基于最新版本。
- **不直接写**：agent 只产出建议，写回需用户在界面确认。
- **写回开关**：`LARK_WRITEBACK=0` 可全局禁用写回（仅模拟）。

## 风险与边界

- 周报含嵌入电子表格/多维表格/画板时，一期仅展示 token 标记，不下钻（需切 lark-sheets/lark-base）。
- agent 产出的 pattern 必须逐字匹配原文，否则该处 str_replace 会 "no changes"（界面会显示失败）。
- 多处替换顺序执行，每处基于最新版本；若两处 pattern 重叠可能互相影响。
