# Generator State — Iteration 001

## What Was Built
- DocSearchPanel 高度约束 + 内部滚动（results-scroll 容器）
- 跨查询保留 selected（reset 分支不再清 selected）
- 顶部常驻"已选 N 份（当前结果 X · 跨查询 Y）"提示条 + 清空按钮
- WorkspaceView 左栏搜索区从 `shrink-0` 改为 `max-h:42vh / min-h:200px` 的可收缩容器
- App.vue 搜索浮层：卡片加 `max-h-[80vh] flex flex-col`，内部包裹层 `flex-1 min-h-0 overflow-hidden flex flex-col`

## What Changed This Iteration

### web/src/components/DocSearchPanel.vue（重写）
- 根 div: `flex flex-col gap-3 h-full min-h-0`（compact 仍控制是否带 `p-4`）
- 搜索框 / 错误 / 选中提示 / 空状态 / 导入按钮均加 `shrink-0`
- 新增 `selectedCount` / `selectedInCurrent` / `selectedCrossQuery` computed
- 结果列表外层改成 `results-scroll flex-1 min-h-0 overflow-y-auto flex flex-col gap-2 pr-1`，分页按钮放进滚动容器末尾（统一滚动）
- `doSearch(reset)` 只清 `results` + `pageToken`，**保留** `selected`
- 新增 `clearSelected()`；`onImport()` emit 后仍清空 selected
- 新增 `toggle(url)` 空值守卫（url 缺失不入集合）
- 滚动条样式 scoped：`--color-outline-variant` / hover `--color-outline`，宽度 6px；Firefox 用 `scrollbar-width: thin`
- 选中项配色改用 `--color-secondary-container` / `--color-primary`，替换原硬编码 `rgba(99,14,212,…)`，符合"复用 token、不硬编码颜色"约束
- 导入按钮文字附带选中数 `(N)`，原"已选 N 份"行下沉到顶部常驻提示，避免重复

### web/src/components/WorkspaceView.vue
- 左栏搜索区容器：去掉 `shrink-0`，改 `flex flex-col min-h-0` + `maxHeight:42vh / minHeight:200px`
- 内部新增 `flex-1 min-h-0 flex flex-col` 包裹层，让 DocSearchPanel 拿到剩余高度
- 标签行加 `shrink-0`

### web/src/App.vue
- 浮层卡片加 `max-h-[80vh] flex flex-col`
- header 加 `shrink-0`
- 包裹 DocSearchPanel 的 `<div class="p-4">` 改为 `p-4 flex-1 min-h-0 overflow-hidden flex flex-col`

## 验证
- `cd web && npm run build` 通过（vite v8, 159ms, 0 错误 0 警告）
- 未引入新依赖、未引入 Pinia/ResizeObserver
- 高亮 v-html 渲染、loadMore 分页、单文档 `urls[0]` 逻辑均未改

## Known Issues
- 浮层模式下 DocSearchPanel 仍带 `p-4`，与父层 `p-4` 叠加产生双层 padding——这是 compact prop 的既有行为，spec 明确保持不动。
- 搜索区 `max-h:42vh / min-h:200px` 是固定阈值，spec V9 指出 600x500 视窗也要不出屏；42vh × 500 ≈ 210px，仍 ≥ minHeight 200px，无溢出风险；侧栏在更矮屏幕下若需更激进收缩可改为更小 min-h，但当前满足 spec。

## Dev Server
- 由 evaluator 启动，本次未启动
- 命令: `cd web && npm run dev`（端口 5173）
