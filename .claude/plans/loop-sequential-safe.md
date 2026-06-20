# Loop Runbook: sequential · safe

> 由 `/loop-start sequential --mode safe` 生成。目标:把飞书周报 Agent 完善到可用。
> 生成日期:2026-06-20。

## 1. 元信息

| 项 | 值 |
|---|---|
| 模式 | `sequential`(顺序迭代,每轮聚焦一个小目标) |
| 安全档 | `safe`(严格质量门 + checkpoint,每轮改动需验证通过才进下一步) |
| 模型策略 | 主循环继承会话模型 `glm-5.2`;verify/review 阶段同模型,不额外升级 |
| 目标 | 完善项目到可用:可启动、有测试、lint 通过、前端可构建 |
| 停止条件 | **连续 3 轮迭代无有效改动(no-progress=3)即停**;或所有 Step 完成 |
| 硬上限 | 最多 12 轮(防止无进展计数失效时 runaway) |

## 2. 启动前安全检查(已执行)

| 检查项 | 结果 |
|---|---|
| git 状态 | ⚠️ `main` 零提交,全部未跟踪 → Step 0 先建基线提交 |
| 测试存在 | ❌ 仓库无任何测试 → Step 1 建立 |
| `ECC_HOOK_PROFILE` | 未设置(未禁用)→ 启动命令显式 `export ECC_HOOK_PROFILE=safe` |
| 工具链 | ✅ `uv` / `node v24.13.1` / `lark-cli` 均在 PATH |
| 显式停止条件 | ✅ no-progress=3 + 硬上限 12 轮 |

> 注:`safe` 模式要求"首次迭代前测试通过"。当前无测试,故 Step 1 建测试本身即首轮任务,建完后从第 2 轮起执行"测试必须通过"的门禁。

## 3. 每轮通用流程(safe 门禁)

```
1. 选取下一个未完成 Step(按下文优先级)
2. 最小必要改动实现该 Step
3. 跑验证门:
   - 后端:uv run ruff check backend && uv run pytest -q(测试存在后)
   - 前端(若改 web):cd web && npm run build
   - 启动:uv run uvicorn backend.main:app --port 8000 & → curl /api/health → kill
4. 改动若产生有效 diff → no_progress 计数清零;否则 +1
5. checkpoint:每完成一个 Step 做一次 git commit(需用户在 safe 模式确认)
6. 若 no_progress >= 3 或 Step 全完成 → 停止
```

## 4. Step 清单(按优先级)

| # | Step | 验收 | 完成标志 |
|---|---|---|---|
| 0 | 建立初始 git 提交基线 | `git log` 有提交 | ✅ |
| 1 | 后端测试基础:加 pytest 依赖 + `backend/lark/doc_xml.py` 与 `backend/config.py` 单元测试 | `uv run pytest -q` 通过,覆盖 doc_xml 解析与 settings | ✅ |
| 2 | 路由层测试:用 FastAPI TestClient mock lark fetch,测 `/api/health` 与 `/api/doc/apply` 的 `LARK_WRITEBACK=0` 模拟分支 | pytest 通过 | ✅ |
| 3 | lint 配置:加 ruff 到 dev 依赖,`ruff check backend` 无 ERROR | ruff 退出 0 | ✅ |
| 4 | 后端启动健康检查:`uvicorn backend.main:app` 起得来,`/api/health` 返回 200 + JSON | curl 200 | ✅ |
| 5 | 前端构建检查:`cd web && npm run build` 通过(不依赖后端) | build 成功 | ✅ |
| 6 | 文档校对:README 启动步骤与实际一致,`.env.example` 无遗漏关键变量 | 人工核对 | ✅ |

> Step 4/5 需联网或 LLM key 的端点(`/agent/*`)不在本轮验证范围,只验证不依赖外部凭证的部分。

## 5. safe 模式约束

- 每轮改动**最小必要**,不重构无关代码(遵守全局 CLAUDE.md)。
- 不删除/覆盖用户未明确要求处理的内容。
- 高风险命令(`rm -rf`、DB、生产)默认先确认。
- git commit 仅在用户确认后执行(safe checkpoint)。
- 不把验证结果表述成收益承诺。

## 6. 启动与监控命令

```bash
# 启动循环(自定节奏,模型按 runbook 推进 Step)
export ECC_HOOK_PROFILE=safe
# 在 Claude Code 中执行:
#   /loop 读取 .claude/plans/loop-sequential-safe.md 并按 Step 推进,每轮跑验证门,no-progress>=3 停

# 监控循环状态
/ecc:loop-status
```

## 7. 干预

- 暂停/停止:在循环中直接中断,或 `/ecc:loop-status` 查看后用 TaskStop 终止。
- 恢复:重新 `/loop` 读本 runbook,从下一个未完成 Step 继续。
