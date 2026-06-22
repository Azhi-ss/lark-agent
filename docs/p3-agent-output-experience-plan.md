# P3 实施计划：统一 Agent 对话输出与 Artifact 审阅体验

> 状态：待实施  
> 来源：grill-me 决策访谈  
> 范围：单文档编辑模式（editor）+ 方案构建模式（workspace）

## 1. 背景与目标

当前应用有两套输出体验：

- 单文档编辑模式：右侧是指令输入、thinking 折叠、文本回复和修改建议卡片。
- 方案构建模式：已有多轮 messages，但方案产物仍作为独立卡片展示。

这两套体验的数据结构和视觉组织不统一。目标是改成统一的飞书文档协作工具式体验：主画布展示文档或方案，右侧是 ChatGPT/Codex 混合 timeline，artifact 以内联摘要卡 + drawer 完整审阅呈现。

核心原则：

- 文档或方案是主角，agent 是右侧协作侧栏。
- 自然语言回复是可选旁白，不作为唯一事实来源。
- 核心事实由粗粒度步骤事件和 artifact 卡片表达。
- 旧 artifact 可回看，但高风险动作只允许最新 artifact 执行。
- 不做完整历史持久化，本轮只保留当前页面会话内的多轮 timeline。

## 2. 已确认设计决策

### 2.1 输出模式

采用 ChatGPT/Codex 混合型：

- ChatGPT 型：保留自然对话入口和多轮上下文。
- Codex 型：保留执行步骤、状态、产物和等待确认。
- 本应用不做纯聊天，也不做纯工程控制台，而是飞书文档协作工具。

### 2.2 改造范围

两种模式统一一套输出组件：

- 单文档编辑模式使用统一 timeline 展示文档编辑建议。
- 方案构建模式使用统一 timeline 展示方案生成与更新。
- 不过早抽象业务 artifact，公共层只统一 timeline、事件契约和 drawer 框架。

### 2.3 事件模型

采用产品语义事件，不让前端直接消费模型 SDK 语义。

后端 SSE 公共契约：

```json
{ "type": "status", "data": { "label": "分析上下文中" } }
{ "type": "assistant_text", "data": { "text": "..." } }
{ "type": "thinking_summary", "data": { "text": "..." } }
{ "type": "artifact", "data": { "artifact_type": "document_edits", "title": "...", "summary": "...", "payload": {} } }
{ "type": "action_required", "data": { "reason": "writeback_confirmation" } }
{ "type": "complete", "data": {} }
{ "type": "error", "data": { "message": "..." } }
```

规则：

- `artifact` 是统一事件，前端按 `artifact_type` 分发。
- `action_required` 只用于高风险或关键确认，例如写回飞书、覆盖当前方案、清空会话。
- 普通查看、定位、复制、导出不触发 `action_required`。
- thinking 折叠展示摘要，不进入主信息流。

### 2.4 Artifact 展示

采用双层展示：

- timeline 内联 artifact 摘要卡，突出本轮产出了什么。
- 右侧 drawer/panel 展示完整 artifact 和操作。
- 点击 artifact 摘要卡打开 drawer。

业务类型：

- `document_edits`：修改建议摘要、定位、接受/拒绝、未定位复制、写回确认。
- `solution`：方案标题、摘要、markdown 预览、导出、覆盖当前方案。

旧版本规则：

- 当前页面会话内保留多轮 timeline。
- 旧 artifact 可打开查看和复制。
- 旧 artifact 不能执行高风险动作。
- 写回飞书或覆盖当前方案只针对最新 artifact。

### 2.5 步骤粒度

主 timeline 只展示粗粒度步骤：

- 加载上下文
- 分析文档或需求
- 生成产物
- 等待确认
- 完成或错误

更细的定位数量、工具 JSON、block 处理细节放进 artifact 卡片或调试展开区，不进入主 timeline。

### 2.6 视觉与布局

完整视觉重做，产品气质偏飞书文档协作工具：

- 单文档编辑：左侧文档主画布，右侧 agent timeline，drawer 展开修改建议详情。
- 方案构建：主画布可切换“当前方案 / 上下文文档”，默认当前方案；右侧 agent timeline。
- 默认两栏布局，artifact drawer 临时展开。
- 不做纯 ChatGPT 居中聊天，也不做 Codex 工程控制台。

## 3. 实施阶段

### 阶段 1：统一后端事件契约

改造 `/agent/chat` 和 `/agent/solution` 的 SSE 输出，使前端统一消费产品语义事件。

涉及文件：

- `backend/agent/agent.py`
- `backend/api/routes.py`

实现要点：

- 保留底层 Anthropic/代理 SDK 流式处理。
- 将现有 `thinking`、`text`、`done`、`error` 转换为产品语义事件。
- 单文档编辑完成时发出 `artifact_type: "document_edits"`。
- 方案构建完成时发出 `artifact_type: "solution"`。
- 高风险确认状态用 `action_required` 表达。

### 阶段 2：前端统一 timeline

新增通用组件：

- `ConversationTimeline.vue`
- `TimelineMessage.vue`
- `StatusStep.vue`
- `ThinkingSummary.vue`
- `ArtifactCard.vue`
- `ArtifactDrawer.vue`

改造点：

- `AgentPane` 和 `WorkspaceView` 都维护 `timelineItems`。
- user message、assistant status、assistant text、thinking summary、artifact、error 都追加到 timeline。
- 支持当前页面内多轮回看。
- 刷新丢失可以接受，本阶段不做完整持久化。

### 阶段 3：artifact 类型分发

前端公共组件只认识统一 artifact 外壳：

```ts
interface AgentArtifact {
  artifact_type: 'document_edits' | 'solution'
  title: string
  summary: string
  payload: unknown
}
```

业务组件按类型处理：

- `DocumentEditsArtifact.vue`
- `SolutionArtifact.vue`

`document_edits` 需要保留现有能力：

- replacement 定位到 block。
- 可定位建议支持定位、接受、拒绝。
- 未定位建议支持复制内容。
- 只有最新 artifact 才允许触发写回确认。

`solution` 需要保留现有能力：

- 更新当前方案主画布。
- 展示标题、摘要和 markdown。
- 支持导出 markdown。
- 只有最新 artifact 才允许覆盖当前方案。

### 阶段 4：完整视觉重做

重排界面为统一工作台：

- 顶部保留全局文档 URL、模式切换、设置入口。
- 主区域左侧为主画布，右侧为 agent 协作侧栏。
- artifact drawer 从右侧或主画布侧展开，不永久挤压主画布。
- 空态、加载态、错误态、等待确认态统一设计。
- 移动端采用画布和 agent 侧栏切换，而不是硬塞双栏。

单文档编辑主画布：

- 保留逐 block 编辑和建议合并能力。
- 修改建议详情从 drawer 审阅。
- 写回按钮仍强调真实修改飞书文档。

方案构建主画布：

- 默认显示当前方案。
- 可切换到上下文文档列表。
- 上下文文档不再压缩 agent timeline。

### 阶段 5：测试与验收

补前端测试：

- SSE 产品事件解析。
- timeline 多轮追加。
- artifact drawer 打开旧版本只读。
- 最新 `document_edits` 才允许高风险写回。
- `solution` artifact 能更新主画布。

跑现有验证：

```bash
pytest
cd web && npm test
cd web && npm run build
```

## 4. 验收标准

功能验收：

- 两种模式都使用统一 timeline 输出。
- 单文档编辑模式仍能生成、定位、接受、拒绝修改建议。
- 方案构建模式仍能生成、更新、导出方案。
- artifact 摘要卡能打开 drawer 查看完整内容。
- 旧 artifact 可查看，但高风险动作禁用。
- 最新 artifact 才能触发写回或覆盖。

体验验收：

- 主画布始终优先展示文档或方案。
- agent 侧栏能清楚表达状态、旁白和产物。
- thinking 摘要默认折叠，不干扰主流程。
- 粗粒度步骤足够说明进展，不暴露底层 JSON 噪音。
- 错误和等待确认状态在 timeline 中清晰可见。

技术验收：

- 前端不直接依赖 Anthropic SDK 风格事件名。
- 新事件契约可兼容未来模型或代理替换。
- 新组件边界清晰，业务 artifact 渲染与 timeline 框架分离。
- 不引入新依赖。

## 5. 主要风险

最大风险是范围偏大：事件模型、两种模式复用、视觉重做会同时影响后端流式输出和前端核心布局。

控制策略：

- 先落事件契约和 timeline，再做视觉重排。
- 先保留现有业务能力，再替换展示层。
- artifact drawer 先支持现有 `replacements` 和 `solution`，不要引入新的业务能力。
- 写回飞书仍沿用现有乐观锁和 block-level apply 逻辑。

## 6. 后续可选扩展

本轮不做，但事件模型应为这些能力留空间：

- 完整会话持久化。
- artifact 版本 diff。
- 开发者调试模式显示完整底层事件和工具 JSON。
- 写回历史和回滚。
- 方案与上下文之间的引用溯源。
