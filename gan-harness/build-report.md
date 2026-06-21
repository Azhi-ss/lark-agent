# GAN Harness Build Report

**Brief:** 打磨前端 UI,修复两个问题:①搜索飞书文档列表过长导致超出屏幕;②换搜索词后之前选中的文档无法共同导入
**Result:** ✅ PASS
**Iterations:** 1 / 15
**Final Score:** 8.85 / 10
**Start:** 2026-06-20

## Score Progression

| Iter | Design | Originality | Craft | Functionality | Total |
|------|--------|-------------|-------|---------------|-------|
| 1    | 9 (0.25) | 8 (0.15) | 9 (0.25) | 9 (0.35) | **8.85** |

迭代 1 即超过 pass_threshold(7.0),循环停止。

## Bug 修复验证

### Bug 1:搜索列表超屏 ✅
- 根因:DocSearchPanel 结果列表无高度约束;WorkspaceView 搜索区 `shrink-0` 无限撑高;App.vue 浮层无 max-height
- 修复:`flex-1 + min-h-0 + overflow-y-auto` 三件套约束结果区;WorkspaceView 搜索区 `maxHeight:42vh / minHeight:200px`;App.vue 浮层 `max-h-[80vh] flex flex-col`;flex 链每级 `min-h-0` 完整

### Bug 2:换词丢失选中 ✅
- 根因:`doSearch(reset=true)` 清空了 `selected`
- 修复:reset 只清 results + pageToken,保留 selected;新增 `selectedInCurrent`/`selectedCrossQuery` computed;顶部常驻提示"已选 N 份(当前 M · 跨查询 K)";导入时一并带出跨查询选中,导入后清空

## Remaining Issues (来自最终评估)

1. **无运行时交互验证**:环境无 Playwright,降级为 code-only + headless Chrome 首屏截图。V1–V9 交互流为代码静态推断,未实际点击验证。Functionality 因此 9 而非 10。
2. **底部导入按钮文案重复**:底部"导入到上下文(N)"的 (N) 与顶部"已选 N 份"数字重复,轻微冗余。
3. **浮层双重 padding**:App.vue 浮层 `p-4` 与 DocSearchPanel `p-4` 叠加(spec 允许,未扣分但可优化)。

## Files Created

- `gan-harness/config.md` — harness 配置
- `gan-harness/spec.md` — 产品规格(planner 生成)
- `gan-harness/eval-rubric.md` — 评估标准(planner 生成)
- `gan-harness/generator-state.md` — generator 迭代状态
- `gan-harness/feedback/feedback-001.md` — 迭代 1 评估反馈
- `gan-harness/build-report.md` — 本报告

## Code Changes (git commit 67b66e2)

| 文件 | 改动 |
|------|------|
| `web/src/components/DocSearchPanel.vue` | 高度约束三件套 + 跨查询选中保留 + 常驻提示 + 清空按钮 + token 化选中态 |
| `web/src/components/WorkspaceView.vue` | 左栏搜索区去 shrink-0 + maxHeight/minHeight + flex 链 |
| `web/src/App.vue` | 搜索浮层卡片 max-h-[80vh] flex flex-col + 内层 min-h-0 |

## Cost & Time

- 3 个 agent 调用(planner + generator + evaluator)
- 子 agent 总 tokens: planner 19k + generator 30k + evaluator 192k(含服务启动/截图/反复验证)
- 主要耗时在 evaluator 启动前后端服务 + headless Chrome 截图
