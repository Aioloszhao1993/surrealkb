# 前端架构说明

> React 18 + Vite + React Router 6 的单页应用（SPA），无状态管理库、无 UI 框架，纯手写 CSS 实现超现实视觉。

---

## 一、技术选型

| 关注点 | 选择 | 为什么 |
|---|---|---|
| 构建工具 | **Vite 5** | 秒级冷启动、HMR 快 |
| 框架 | **React 18** | 函数组件 + Hooks |
| 路由 | **React Router 6** | `BrowserRouter` + `Routes/Route` |
| HTTP | **axios 1.x** | 用拦截器统一加 token / 处理 401 |
| 状态管理 | **React Context**（自己写） | 项目小，不引入 Redux/Zustand |
| 样式 | **原生 CSS + CSS 变量** | 一个 `styles.css` 撑起整个设计系统 |
| UI 库 | 无 | 手写组件，风格完全可控 |

---

## 二、目录结构

```
frontend/
├─ index.html                # SPA 挂载点（<div id="root">）
├─ vite.config.js            # 端口 5173 + /api、/media 代理到 8000
├─ package.json
└─ src/
   ├─ main.jsx               # 入口：ReactDOM + BrowserRouter + AuthProvider
   ├─ App.jsx                # 路由表 + RequireAuth 守卫 + 全局布局
   ├─ styles.css             # 超现实设计系统（唯一 CSS 文件）
   ├─ api.js                 # axios 实例 + 请求/响应拦截器
   ├─ store.jsx              # AuthContext（登录态 + login/register/logout/applyToken）
   ├─ presets.js             # 8 款霓虹预设头像（内联 SVG data URL）
   ├─ components/            # 可复用展示组件
   │  ├─ Background.jsx      # 极光光球动态背景
   │  ├─ Navbar.jsx          # 顶栏（品牌/搜索/导航/账号菜单/微信登录）
   │  ├─ DocCard.jsx         # 文档卡片
   │  ├─ AiChat.jsx          # 右下角 AI 助手悬浮面板
   │  ├─ Avatar.jsx          # 统一头像渲染（支持 /media 路径 与 data URL）
   │  ├─ AvatarPicker.jsx    # 头像选择（预设 + 上传）
   │  ├─ PresetGrid.jsx      # 预设头像网格
   │  ├─ EditProfile.jsx     # 编辑昵称 + 个性签名
   │  ├─ UserHoverCard.jsx   # 悬停资料卡（类 B 站）
   │  ├─ AccountMenu.jsx     # 账号下拉菜单（顶栏只显示头像）
   │  ├─ WechatLogin.jsx     # 微信扫码登录弹窗
   │  └─ format.js           # 数字/时间/体积格式化
   └─ pages/                 # 路由级页面
      ├─ Home.jsx            # 首页：文档列表 + 搜索 + 状态筛选 + 分页
      ├─ DocDetail.jsx       # 文档详情：分块列表 + 改名/重建索引/删除 + 问问 AI
      ├─ Upload.jsx          # 上传页：拖拽/点选 + 进度条
      ├─ Login.jsx           # 登录
      ├─ Register.jsx        # 注册（可选创建/加入知识库 + 头像）
      ├─ Profile.jsx         # 用户主页（某作者上传的文档）
      └─ Team.jsx            # 知识库：创建 / 邀请码加入 / 成员列表
```

---

## 三、分层心智模型

```
main.jsx（启动）
   └─ BrowserRouter        路由能力
       └─ AuthProvider     全局登录态（Context）
           └─ App.jsx      布局 + 路由分发
               ├─ Background / Navbar / footer / AiChat   全局壳
               └─ <Routes>  按 URL 渲染 page
                       └─ page  内部调 api.js 取数据 → 用 component 渲染
```

**页面（pages）** 负责「取数据 + 组装」；
**组件（components）** 只负责「渲染」，尽量无状态；
**api.js** 是唯一与后端通信的出口；
**store.jsx** 是唯一的全局状态。

---

## 四、核心机制

### 1. 路由与权限守卫（App.jsx）

| 路径 | 页面 | 是否需要登录 |
|---|---|---|
| `/` | Home | 否（登录后才加载文档） |
| `/doc/:id` | DocDetail | 否 |
| `/login` `/register` | 登录/注册 | 否 |
| `/user/:id` | Profile | 否 |
| `/upload` | Upload | ✅ `RequireAuth` |
| `/team` | Team | ✅ `RequireAuth` |
| `*` | 404 | 否 |

`RequireAuth` 逻辑：`ready` 未就绪 → 显示「加载中」；未登录 → `<Navigate to="/login" state={{from}} />`（登录后回跳原页）。

### 2. axios 拦截器（api.js）

- **请求拦截**：自动从 `localStorage` 取 token 塞进 `Authorization: Bearer`
- **响应拦截**：遇到 401 就清掉本地登录态并跳登录页
- `errMsg(err)` 统一把后端错误转成可读文案（兼容 FastAPI 的 422 数组）

### 3. 登录态（store.jsx）

`AuthProvider` 用 Context 暴露 `{ user, ready, login, register, logout, applyToken, updateUser }`。
- 初始从 `localStorage` 读 `user`，随后用 `/auth/me` 校验 token 是否仍有效
- `login/register` 成功后把 token + user 写入 `localStorage`
- `applyToken`（微信扫码成功 / 头像更新后写回）、`updateUser`（改昵称后同步）
- `useAuth()` 是消费入口（在 Provider 外调用会抛错）

### 4. 数据获取模式

没有用 React Query / SWR，统一是 **`useEffect` + `api.get` + `useState`**：

```jsx
const [data, setData] = useState({ items: [], total: 0 })
useEffect(() => {
  api.get('/documents', { params: {...} }).then(({ data }) => setData(data))
}, [依赖])
```

列表类页面（Home / Profile）共用同一个返回结构 `DocumentPage { items, total, page, page_size }`。

### 5. 样式系统（styles.css）

靠 **CSS 变量**统一主题，无 Tailwind：
- 变量：`--bg-0/1`（深空底）、`--panel`（玻璃面板）、`--neon-1~4`（紫/青/粉/金）
- 特效类：`.orb`（模糊光球 + 浮动动画）、`.grid-overlay`（网格）、`.noise`（噪点）
- 玻璃拟态：`backdrop-filter: blur()` + 半透明边框
- 动效：卡片悬停上浮 + 光晕、按钮过渡
- 响应式：`@media (max-width: 720px)` 收窄布局

### 6. 上传进度（Upload.jsx）

- **拖拽 + 点选**都支持：`onDragEnter/Over/Leave/Drop` 用计数器（`dragDepth`）避免子元素导致的抖动；拖入文件先校验扩展名，不支持就提示。
- 用 axios 的 `onUploadProgress` 把 `loaded/total` 换算成百分比，驱动进度条。
- 表单用 `FormData` 带 `title`（可选）+ `file`；成功后跳文档详情页。

### 7. 账号与社交细节

- 顶栏登录后**只显示头像**（`AccountMenu`），悬停放大并弹出资料卡（`UserHoverCard`，类 B 站）。
- 头像统一由 `Avatar.jsx` 渲染，兼容后端返回的 `/media/...` 相对路径与内联 `data:image/svg+xml` 预设。
- 注册页可选**创建知识库**或**用邀请码加入**，并可顺带选头像。
- 文档详情页「问问 AI」= `dispatchEvent(new CustomEvent('ai-ask', {detail}))`。

---

## 五、AI 助手面板（AiChat.jsx）

一个自包含的悬浮组件，不依赖任何 UI 库：

- **悬浮球**（`.ai-fab`）：固定右下角，点击开合面板。
- **面板**（`.ai-panel`）：头部（标题 + 清空 + 关闭）、消息区、输入框。
- **打字机效果**：后端返整段答案后，前端逐字吐出（`setInterval` 切片）。
- **引用胶囊**：`data.sources` 渲染成一排小胶囊，点击跳 `/doc/{document_id}`。
- **会话保持**：`session_key` 用 `useRef` 生成一次并写 localStorage，刷新后点开还能看到历史；该标识改用 `X-Session-Key` 请求头传递给后端（不再拼进 URL），后端按「用户 + 会话」双重隔离。未登录时点「问问 AI」会提示先登录。
- **外部唤起**：监听 `window` 的 `ai-ask` 自定义事件。文档详情页的「✦ 问问 AI」按钮就是派发该事件，面板自动打开并提问。
- **开关联动**：挂载时探一次 `/api/ai/status`，后端没配 Key（`enabled:false`）就不渲染入口。

---

## 六、开发/构建

```powershell
cd D:\surreal_kb\frontend
npm install
npm run dev        # 开发：http://localhost:5173（/api、/media 自动代理到 8000）
npm run build      # 产物在 dist/
npm run preview    # 本地预览构建产物
```

> ⚠️ 开发时请访问 `http://localhost:5173`（不是 `127.0.0.1:5173`）：Vite 绑定的可能是 IPv6 `::1`。

生产部署：`dist/` 交给 Nginx，把 `/api`、`/media` 反代到后端即可（此时无需 Vite 代理）。

---

## 七、可扩展点（如果要做大）

- 请求缓存/重试：引入 TanStack Query
- 全局状态变多时：引入 Zustand
- 组件库/设计系统：可迁移到 Tailwind 或 shadcn/ui
- 路由懒加载：`React.lazy` + `Suspense` 拆包
- 文档在线预览、评论、多知识库切换：新增对应 page + 后端接口
