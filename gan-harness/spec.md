# Product Specification: DocSearchPanel UI 打磨

> Generated from brief: "打磨前端 UI，修复两个问题：搜索结果列表撑破父容器；换搜索词后丢失已选文档"

## Vision
DocSearchPanel 是 Lark Agent 前端唯一的飞书文档搜索入口，被两种容器复用（方案构建模式左栏 / 单文档编辑模式浮层）。这次打磨的目标：让搜索体验在任何容器里都"装得下、选得住"——结果列表始终在固定视窗里内部滚动，跨查询的多选状态可以累积到一次导入里去。修复要最小、克制，不引入 UI 风格变化。

## 问题陈述（Root Cause）

### Bug 1：搜索结果列表撑破父容器
- `DocSearchPanel` 的结果列表 `<div class="flex flex-col gap-2">`（第 117 行）**没有任何高度上限**，结果项按内容自然堆叠。
- 在 **WorkspaceView.vue 侧栏**（第 280 行 `<div class="px-4 py-3 shrink-0 border-b">`）里，整个搜索区被父容器标注为 `shrink-0`，意味着"不允许收缩"，结果列表越长，搜索区高度越大，把下方"文档列表"（`flex-1 overflow-y-auto`）挤出可视区域。
- 在 **App.vue 浮层**（第 305-345 行 `Teleport` + `items-start pt-20`）里，浮层 `<div class="w-[560px] ... overflow-hidden">` 没设 `max-height`，结果多了之后浮层自身超出视窗，底部"导入"按钮被挤出屏幕外，且因为 `items-start pt-20` 无法靠 flex 居中救回。

### Bug 2：换搜索词后丢失已选
- `DocSearchPanel.doSearch(reset=true)`（第 30-37 行）在 reset 分支里同时清空了 `results`、`pageToken` 和 `selected`。
- 用户体验路径：搜 "OKR" 勾选 2 份 → 换关键词搜 "周报" → 勾选 1 份 → 点"导入到上下文"，只会带 1 份；前面 2 份在第二次 `onEnter()` 时就丢了，且没有任何提示。

## 目标（Definition of Done）

| # | 目标 | 验证场景 |
|---|------|----------|
| G1 | 侧栏内嵌的搜索面板永远不挤压下方文档列表 | WorkspaceView 左栏：搜 "项目"，返回 15 条，文档列表区仍可见且可滚动 |
| G2 | 浮层模式下面板永远不超出视窗，导入按钮始终可见 | 单文档模式：搜返回 15 条，浮层底部"导入"按钮在视窗内 |
| G3 | 结果列表在自身区域内滚动，滚动条样式与 Material You 主题一致 | 滚动时无父级滚动联动；滚动条颜色用 `var(--color-outline)` 系 token |
| G4 | 换关键词搜索保留已选 | 搜 A 勾 2 → 搜 B 勾 1 → 共选 3，点导入 emit 3 个 URL |
| G5 | 选中状态有明确视觉提示，区分"本次结果中"和"跨查询" | 顶部常驻一行"已选 N 份（含跨查询 M 份）"，N≥1 时常驻 |
| G6 | 导入后清空全部跨查询选中 | onImport 后 selected.size === 0 |

## 范围

### In Scope
- `web/src/components/DocSearchPanel.vue`：核心修改（高度约束、selected 生命周期、跨查询提示）
- `web/src/components/WorkspaceView.vue`：搜索区父容器布局（让其可收缩并向子组件传递高度）
- `web/src/App.vue`：浮层容器加 `max-height` 和内部滚动

### Out of Scope
- 后端 `/api/docs/search` 接口、参数、高亮逻辑
- 搜索触发时机（仍是回车/按钮）
- 分页（loadMore）逻辑
- 单文档模式"取首份"逻辑（`onImportToEditor` 在 App.vue 内）
- 任何 Material You token / 配色 / 字体调整

## 详细需求

### R1：结果列表高度约束策略
DocSearchPanel 内部把结果列表（含分页按钮）包成一个**可滚动的滚动容器**：

```
<div class="results-scroll flex-1 min-h-0 overflow-y-auto">
  v-for results …
  v-if hasMore loadMore button
</div>
```

外层根容器从 `flex flex-col gap-3` 改成 `flex flex-col gap-3 min-h-0 h-full`（在 compact 下）+ 搜索框 / 错误 / 顶部"已选"提示 / 导入按钮 都是 `shrink-0`，**只有 results-scroll 是 flex-1**。

容器侧的约束：

| 容器 | 父级修改 | 子组件靠什么拿到高度 |
|------|----------|----------------------|
| WorkspaceView 侧栏 | 搜索区 `<div class="px-4 py-3 shrink-0 border-b">` 改成 `flex flex-col` 并把 `shrink-0` 去掉，外层左栏父容器保持 flex 列布局，使搜索区可与文档列表瓜分剩余空间；或给搜索区设 `max-h-[42vh] min-h-[200px]` 上限 | DocSearchPanel 内部 results-scroll `flex-1 min-h-0 overflow-y-auto` |
| App.vue 浮层 | 浮层卡片 `<div class="w-[560px] ...">` 加 `max-h-[80vh] flex flex-col`；header `shrink-0`；包 DocSearchPanel 的 `<div class="p-4">` 改成 `<div class="p-4 flex-1 min-h-0 overflow-hidden flex flex-col">` | 同上 |

**关键 CSS 链**：每一级 flex 子项都要 `min-h-0`，否则 `overflow-y-auto` 不生效（flex 默认 `min-height: auto` 会拒绝收缩）。

滚动条样式（scoped）：
```css
.results-scroll::-webkit-scrollbar { width: 6px; }
.results-scroll::-webkit-scrollbar-thumb {
  background: var(--color-outline-variant);
  border-radius: 3px;
}
.results-scroll::-webkit-scrollbar-thumb:hover {
  background: var(--color-outline);
}
```

### R2：跨查询保留选中

`doSearch(reset)` 改造：reset 分支**只清 results 和 pageToken，不再清 selected**。

```js
if (reset) {
  results.value = []
  pageToken.value = ''
  // selected 保留，跨查询累积
}
```

新增派生量：
- `selectedCount` = `selected.size`
- `selectedInCurrent` = 当前 results 里 url 命中 selected 的数量
- `selectedCrossQuery` = `selectedCount - selectedInCurrent`

UI：当 `selectedCount > 0` 时，在搜索框下方常驻一行提示条（`shrink-0`）：

```
已选 {{ selectedCount }} 份
（当前结果 {{ selectedInCurrent }} · 跨查询 {{ selectedCrossQuery }}）   [清空]
```

- "清空"按钮：调 `selected.value = new Set()`
- 文字色 `var(--color-on-surface-variant)`，跨查询数字用 `var(--color-primary)` 加重
- `selectedCount === 0` 时不渲染，避免空状态噪音

底部"导入到上下文"按钮的 `v-if="selected.size > 0"` 行为不变；`onImport` emit 完整 `[...selected]`，emit 后 `selected.value = new Set()`，保持原语义。

### R3：不破坏的现有行为
- v-html 高亮渲染（后端仅允许 `<mark>`）：保持
- 分页 loadMore：保持（loadMore 走 `doSearch(false)`，从不动 selected）
- 单文档模式 `onImportToEditor` 取 `urls[0]`：保持，但多选导入时仍接收完整数组（取首份是 App.vue 的选择，不归本次修复）
- 搜索框 / 搜索按钮 / 空状态 / 错误提示样式：保持
- compact prop：保持（仅控制 `p-4` 是否生效）

## 验证点（手动 QA 脚本）

| # | 步骤 | 期望 |
|---|------|------|
| V1 | WorkspaceView 模式 → 搜 "项目"（返回 ≥10 条）| 搜索区不撑破侧栏，下方"文档列表"标题可见，列表区可滚动 |
| V2 | 同上，结果列表内滚动 | 滚动条出现在结果区内部，宽度 6px，颜色为 outline-variant |
| V3 | App.vue 模式 → 点搜索图标 → 搜 "OKR" | 浮层不超过视窗高度 80%，底部"导入到上下文"按钮可见 |
| V4 | 搜 "A" 勾 2 条 → 输入 "B" 回车 | results 重置为 B 的结果；顶部提示"已选 2 份（当前 0 · 跨查询 2）" |
| V5 | 接 V4 → 勾 B 中 1 条 | 提示变为"已选 3 份（当前 1 · 跨查询 2）" |
| V6 | 接 V5 → 点导入到上下文 | emit 数组 length === 3；emit 后 selected 清空，提示条消失 |
| V7 | 选中后点"清空" | selected 立即清空，提示条消失，结果列表勾选态同步取消 |
| V8 | 加载更多分页 | selected 不变，新追加的项可继续勾选累加 |
| V9 | 浏览器窗口缩到 600x500 | 浮层依旧不出屏，结果区滚动正常 |

## 反例（要避免的实现）
- 直接给结果列表设固定 `max-h-[400px]`：不响应视窗，浮层在小屏依旧溢出
- 用 `overflow-hidden` 截断而非 `overflow-y-auto`：用户看不到下面的项
- 给整个 DocSearchPanel 套 `max-h-[80vh]`：搜索框和导入按钮也会被滚动带走
- 在 WorkspaceView 父级加 `overflow-y-auto`：会把"文档列表"区也一起滚，破坏其内部滚动
- 把 selected 升级成全局 store / pinia：过度设计，本组件局部状态即可
- 引入"历史搜索词记录"或"清空时确认弹窗"：超出范围

## 技术栈
- Vue 3 `<script setup>` + Composition API（`ref` / `computed`）
- Tailwind utility classes + 内联 `:style` 取 Material You CSS 变量
- 无新增依赖
