# GAN Harness Config

**Brief**: 打磨前端 UI,修复两个问题:
1. 搜索飞书文档列表过长导致超出屏幕
2. 换搜索词后,之前选中的文档无法共同导入

**Configuration**:
- max_iterations: 15
- pass_threshold: 7.0
- skip_planner: false
- eval_mode: playwright
- start_time: 2026-06-20

**Project context**:
- 前端: Vue3 + Vite, web/src/
- 后端: FastAPI, backend/ (uvicorn :8000)
- 搜索组件: web/src/components/DocSearchPanel.vue
- 两处使用: WorkspaceView.vue(方案构建左栏) + App.vue 搜索浮层(单文档编辑)
- dev server: cd web && npm run dev (5173)

**Known bugs to fix**:
1. DocSearchPanel 结果列表无高度约束 → 超屏。方案构建左栏搜索区是 shrink-0 会无限撑高;单文档浮层列表无 max-height。
2. doSearch(reset=true) 时 selected = new Set() 清空了跨查询选中 → 换词后选中丢失。
