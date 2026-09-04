# 智能旅行助手 - 前端

基于 Vue 3 + Vite + TypeScript 的智能旅行规划 Web 应用前端。采用**混合式交互**：用户自然语言输入 → AI 意图识别 → 表单自动填充确认 → 生成详细行程。

## 技术栈

| 类别 | 技术 | 版本 |
|------|------|------|
| 框架 | Vue 3 (Composition API) | ^3.5 |
| 构建工具 | Vite | ^6.0 |
| 语言 | TypeScript | ^5.7 |
| UI 组件库 | Ant Design Vue | ^4.2 |
| 路由 | Vue Router | ^4.5 |
| HTTP | Axios | ^1.7 |
| Markdown 渲染 | marked | ^18.0 |
| 地图 | 高德地图 JS API | - |
| 导出 | html2canvas + jsPDF | - |

## 项目结构

```
frontend/
├── index.html                  # 入口 HTML
├── package.json
├── vite.config.ts              # Vite 配置（含 /api 代理到 localhost:8000）
├── .env                        # 环境变量（后端地址、高德 Key）
├── tsconfig.json
└── src/
    ├── main.ts                 # 应用入口，引入全局样式
    ├── App.vue                 # 根组件，Ant Design 中文 locale 配置
    ├── components/
    │   ├── AppSidebar.vue      # 侧边栏（品牌/新建对话/历史列表/偏好管理/折叠）
    │   ├── ChatHeader.vue      # 聊天区顶部栏（标题/AI 状态指示）
    │   ├── EmptyState.vue      # 空状态（品牌图标 + 快捷建议 chips）
    │   ├── ChatComposer.vue    # AI 输入框（textarea 自动高度/Enter发送/Shift+Enter换行）
    │   ├── PreferencesModal.vue # 偏好管理弹窗（默认出发地/交通/住宿/偏好标签）
    │   └── HistoryPanel.vue    # 历史面板（对话历史/行程足迹/偏好管理 3 Tab，从后端拉取）
    ├── views/
    │   ├── Home.vue            # 主页面（聊天+表单确认+行程结果+SSE流式，核心业务逻辑）
    │   └── Result.vue          # 行程结果详情页（预留）
    ├── services/
    │   ├── api.ts              # API 请求封装（Axios + fetch/SSE 流式解析）
    │   └── intent.ts           # 前端兜底意图识别（当前已接后端 /api/chat/intent）
    ├── styles/
    │   └── tokens.css          # Design Tokens（颜色/间距/圆角/阴影/字体/动画）
    └── types/
        └── index.ts            # 类型定义（TripFormData / TripPlan / ChatMessage 等）
```

## 快速开始

### 环境要求

- Node.js >= 18
- npm >= 9

### 安装依赖

```bash
cd frontend
npm install
```

### 开发模式

```bash
npm run dev
```

启动后访问 `http://localhost:5173`。Vite 支持热更新（HMR），修改代码自动刷新。

> 端口 5173 被占用时 Vite 会自动递增到 5174。

### 生产构建

```bash
npm run build
```

产物输出到 `dist/` 目录。

### 预览构建产物

```bash
npm run preview
```

## 核心功能

### 混合式交互流程

```
用户输入（自然语言）
    ↓
意图识别（调用后端 /api/chat/intent，含长期记忆上下文）
    ↓ 识别为行程规划
提取关键信息（目的地/日期/天数/交通/偏好）
    ↓
自动填充行程确认表单
    ↓
用户确认或补充信息
    ↓
确认并生成行程 → 调用后端 /api/chat/form-plan/stream（SSE 流式，打字机效果）
    ↓
Markdown 渲染行程结果
```

未指定出发日期时默认当天，用户可在表单中修改。

非行程意图（普通问答 / RAG / 记忆 / 偏好）走 `/api/chat/message/stream`（SSE 流式），边生成边展示节点进度与逐字回复。

### 侧边栏

- 新建对话、历史对话列表（localStorage 持久化，最多 50 条）
- 偏好管理（默认出发城市、交通方式、住宿偏好、旅行偏好标签）
- 折叠/展开（折叠后 64px，仅显示图标）
- 历史记录入口（打开右侧 HistoryPanel：对话历史/行程足迹/偏好管理 3 Tab）

### 历史面板（HistoryPanel）

- **💬 对话历史**：从后端 `/api/chat/history` 拉取完整对话时间线（含统计卡片、常去目的地标签）
- **🧳 行程足迹**：后端长期记忆中的历史行程卡片（南京→杭州 / 南京→西安 等）
- **⚙️ 偏好管理**：偏好增删改，改动同步保存到后端长期记忆（`/api/preferences`）

### AI 对话体验

- AI 消息 Markdown 渲染（标题/列表/加粗/代码/表格/引用）
- 消息进入动画 + 平滑自动滚动
- AI 消息操作栏（复制 / 重新生成，常驻显示）
- 消息时间戳
- 空状态快捷建议（杭州 3 日游 / 成都 5 日游 等）
- AI 思考中 loading 状态

### 表单确认

- 出发城市、目的地城市、开始日期（中文日期选择器）
- 旅行天数、交通方式、住宿偏好
- 旅行偏好多选标签（历史文化/自然风光/美食/购物/艺术/休闲）
- 额外要求自由输入
- 自动计算行程结束日期

## 环境变量

在 `.env` 文件中配置：

```env
# 后端 API 地址
VITE_API_BASE_URL=http://localhost:8000

# 高德地图 Web API Key
VITE_AMAP_WEB_KEY=your_amap_web_key

# 高德地图 Web 端 JS API Key
VITE_AMAP_WEB_JS_KEY=your_amap_js_key
```

开发模式下 Vite 会将 `/api` 请求代理到 `http://localhost:8000`（见 `vite.config.ts`）。

## 设计系统

全局 Design Tokens 定义在 `src/styles/tokens.css`，包括：

- **颜色**：主色（蓝紫 `#5B5FC7`）、背景、表面、文本三级、边框
- **间距**：4 / 8 / 12 / 16 / 20 / 24 / 32 / 40 / 48px
- **圆角**：sm 8px / md 12px / lg 16px
- **阴影**：极弱阴影为主，配合边框
- **字体**：系统字体栈，正文 14px / 行高 1.7
- **动画**：fast 150ms / normal 250ms，消息进入 0.3s ease

## 后端接入说明

前端已对接真实后端（FastAPI + LangGraph，见 `backend/README.md`）：

- 意图识别：`/api/chat/intent`（`src/services/api.ts` → `fetchIntent`）
- 通用对话：`/api/chat/message/stream`（SSE 流式，节点进度 + 逐字输出）
- 表单行程规划：`/api/chat/form-plan/stream`（SSE 流式，打字机效果）
- 历史/偏好：`/api/chat/history`、`/api/preferences`
- 流式解析：`streamChat()` 用 fetch + ReadableStream 解析 SSE 事件（`api.ts`）

`src/services/intent.ts` 保留为前端兜底（后端不可用时降级），正常流程走后端接口。

## 浏览器兼容

支持现代浏览器（Chrome / Edge / Firefox / Safari 最新两个版本）。桌面端优先，移动端基础响应式适配。
