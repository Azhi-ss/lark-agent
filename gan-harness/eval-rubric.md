# Evaluation Rubric: DocSearchPanel UI 打磨

> 4 个维度，每个维度 1-10 分，加权求和到 10 分制总分。
> 评分对象：本次修复后的 `DocSearchPanel.vue` / `WorkspaceView.vue` / `App.vue` 差异。

## 维度权重

| 维度 | 权重 | 关注点 |
|------|------|--------|
| Functionality | 0.35 | 两个 Bug 是否真正修复，回归是否清零 |
| Design | 0.25 | 视觉一致性、滚动条体验、与 Material You 主题契合 |
| Craft | 0.25 | 代码质量、复用现有模式、改动克制 |
| Originality | 0.15 | 方案合理性，最小且正确，不过度设计 |

总分 = 0.35×F + 0.25×D + 0.25×C + 0.15×O

---

## Functionality（功能，权重 0.35）

| 分档 | 标准 |
|------|------|
| 10 | V1–V9 全部通过；selected 跨查询累积准确；导入后清空；分页与跨查询协同正确；浮层与侧栏两种容器表现都正确 |
| 9 | V1–V9 通过；跨查询提示文案与"当前 / 跨查询"数字准确；导入 emit 完整数组；浮层 `max-h-[80vh]` 与 `min-h-0` 链路完整 |
| 7 | 两个 Bug 都修复了，但跨查询提示信息不完整（如未拆分"当前 / 跨查询"），或浮层在小屏（高度<600）仍有少量溢出 |
| 5 | 只修复了一个 Bug；或换词保留 selected 了但导入按钮在跨查询场景下行为有误（如 emit 漏项 / 未清空） |
| 3 | Bug 仅在某一种容器下修复（例如侧栏修了浮层没修），或修复引入新回归（分页失效、无法搜索） |
| 1 | 两个 Bug 都没有真正修复，或代码不能运行 |

**关键判定点**：
- 搜 A 勾 2 → 搜 B 勾 1 → 导入 emit 数组 length === 3 ✅
- 结果列表内部滚动，父容器不被撑破 ✅
- 浮层底部"导入到上下文"按钮在窗口 80vh 内可见 ✅
- 导入后 selected 清空，提示条消失 ✅

---

## Design（设计/视觉一致性，权重 0.25）

| 分档 | 标准 |
|------|------|
| 10 | 滚动条 6px、用 `var(--color-outline-variant)` / `:hover` `var(--color-outline)`；跨查询提示文案排版克制，数字用 primary 色加重；与既有 Material You 节奏一致 |
| 9 | 滚动条样式定义到位，颜色用 token；提示条对齐与 spacing（gap-3 / py 系列）与现有组件呼应 |
| 7 | 视觉过得去，但有 1-2 处细节失调：滚动条用浏览器默认样式、或提示文案颜色硬编码 hex |
| 5 | 出现明显风格断裂：用了非 token 的颜色（如 #888 / gray-400）、新字体、emoji、新阴影 |
| 3 | 引入了与主题不一致的组件（如 native `<select>` 默认样式、突兀的边框） |
| 1 | UI 出现明显错位、文字重叠、布局抖动 |

**反例（扣分项）**：
- 用 `bg-gray-50` / `text-gray-500` 替代 CSS 变量
- 加 gradient / glassmorphism 装饰
- 提示条用 emoji（⚠️ 📌 等）

---

## Craft（工艺，权重 0.25）

| 分档 | 标准 |
|------|------|
| 10 | 改动 ≤3 文件、≤80 行；`selectedInCurrent` / `selectedCrossQuery` 用 `computed` 派生；flex 链 `min-h-0` 每一级清晰；注释解释 why（如"selected 跨查询保留，因此不在 reset 中清空"）；无 console.log / 无注释掉的旧代码 |
| 9 | 代码组织清晰，computed 派生正确，命名规范，scoped 滚动条样式 |
| 7 | 功能对，但代码有小瑕疵：用 `watch` 同步派生数据（本应 computed）、内联 style 重复、缺少注释 |
| 5 | 重复实现：在 WorkspaceView 和 App.vue 里各写一份滚动逻辑而不是收敛在 DocSearchPanel 内；或把 selected 提到了父组件 |
| 3 | 复制粘贴大段代码、引入未使用的 import、留 TODO；改动 >150 行 |
| 1 | 破坏既有代码风格（混用 Options API、删除注释、改动无关文件） |

**关键判定点**：
- 是否复用现有 token（`var(--color-*)`）而非 hardcode
- 是否避免不必要的状态升级（selected 应保留在 DocSearchPanel 内部）
- 注释是否解释 why 而非 what
- 是否动了无关代码

---

## Originality（方案合理性，权重 0.15）

| 分档 | 标准 |
|------|------|
| 10 | 高度约束采用 `flex-1 + min-h-0 + overflow-y-auto` 这一标准 Flexbox 模式（最小最正确）；跨查询提示在面板内部解决，不外溢到父组件 |
| 9 | 方案干净直接，没有多余抽象 |
| 7 | 方案可用但稍重：例如用 `ResizeObserver` 动态计算高度、用 CSS variable 传高度——能解决但比纯 flex 复杂 |
| 5 | 过度设计：引入 Pinia store 管理跨查询 selected、加搜索历史、加快捷键面板 |
| 3 | 方案错误但勉强能跑：用 `position: fixed` + 手算 top/bottom 替代 flex 滚动 |
| 1 | 用 `setTimeout` / `scrollIntoView` 等 hack 兜底布局问题 |

---

## 评分输出格式

Evaluator 应输出：

```json
{
  "functionality": {"score": 0-10, "notes": "..."},
  "design":        {"score": 0-10, "notes": "..."},
  "craft":         {"score": 0-10, "notes": "..."},
  "originality":   {"score": 0-10, "notes": "..."},
  "weighted_total": 0.0-10.0,
  "verdict": "pass" | "iterate" | "fail",
  "must_fix":   ["..."],
  "should_fix": ["..."]
}
```

- `pass`：weighted_total ≥ 8.0 且 functionality ≥ 8
- `iterate`：weighted_total ∈ [6.0, 8.0) 或 functionality ∈ [6, 8)
- `fail`：weighted_total < 6.0 或 functionality < 6
