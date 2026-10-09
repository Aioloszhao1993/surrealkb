# SurrealVideo · 超现实视频站

一个极简版 B 站风格视频网站：**上传 / 点赞 / 收藏 / 转发**，外加 **微信扫码登录**、**自定义头像**、**B 站式头像悬停名片 + 关注**，以及一个 **AI 问答助手**，视觉走超现实霓虹风。

- 后端：**FastAPI** + SQLAlchemy 2.0 + JWT
- 前端：**React 18** + Vite + React Router
- 数据库：**MySQL 8**（utf8mb4）
- 登录：账号密码 **+ 微信扫码登录**（微信开放平台网站应用；未配置 AppID 时自动降级为本地 Mock 扫码）
- 头像：预设霓虹头像 / 本地图片上传（/media/avatars）
- 社交：关注 / 粉丝、头像悬停资料卡（B 站同款交互）
- AI：**阿里云百炼（DashScope）** `qwen-plus` + `text-embedding-v3`，手写轻量 RAG（不引入外部向量库）
- 存储：本地 `backend/uploads`，通过 `/media/*` 静态服务

---

## 目录结构

```
video_fastqpi/
├─ backend/
│  ├─ app/
│  │  ├─ main.py          # FastAPI 入口
│  │  ├─ config.py        # 配置（读 .env）
│  │  ├─ database.py      # 引擎 / 会话
│  │  ├─ models.py        # User / Video / Like / Favorite / Follow / VideoEmbedding / ChatMessage / WxLoginState
│  │  ├─ schemas.py       # Pydantic 模型
│  │  ├─ security.py      # bcrypt + JWT
│  │  ├─ deps.py          # 依赖（当前用户）
│  │  ├─ services.py      # 序列化
│  │  ├─ wechat_service.py# 微信扫码登录（真实 + 本地 Mock）+ 生成默认头像
│  │  ├─ ai_service.py    # AI 助手：向量索引 + 手写余弦检索 + 对话
│  │  └─ routers/
│  │     ├─ auth.py       # 注册 / 登录 / 我 / 头像 / 微信扫码
│  │     ├─ users.py      # 用户资料 / 关注 / 作品 / 点赞 / 收藏
│  │     ├─ videos.py     # 视频 CRUD + 互动
│  │     └─ ai.py         # AI 问答 / 历史 / 重建索引
│  ├─ migrate.py          # 轻量迁移（给已有库补新列 / 新表）
│  ├─ sql/init.sql        # 建库脚本
│  ├─ requirements.txt
│  └─ .env.example
└─ frontend/
   ├─ src/
   │  ├─ App.jsx  main.jsx  store.jsx  api.js  styles.css  presets.js
   │  ├─ components/  (Navbar / VideoCard / Background / format / AiChat / Avatar / AvatarPicker / UserHoverCard / EditProfile / WechatLogin)
   │  └─ pages/       (Home / Watch / Upload / Login / Register / Profile / Favorites)
   └─ package.json
```

---

## 一、准备 MySQL

本项目已内置一套**免安装（绿色版）MySQL 8.0**，无需管理员权限，开箱即用。

### 方式 A：使用内置 MySQL（推荐）

```powershell
cd D:\video_fastqpi
.\start-mysql.ps1     # 启动（后台运行，监听 127.0.0.1:3306）
.\stop-mysql.ps1      # 停止
```

已自动完成：
- 解压至 `D:\video_fastqpi\mysql\mysql-8.0.28-winx64`
- 数据目录 `D:\video_fastqpi\mysql_data`（已初始化）
- 建库 `video_fastqpi`（utf8mb4）
- 专用账号：`sv_user` / `<你自己设的密码>`（已授予该库全部权限，与 `backend/.env` 里的 `DB_PASSWORD` 保持一致）

### 进入数据库（命令行）

**双击即用**：直接**双击** `D:\video_fastqpi\mysql-cli.bat` —— 它会先检查 MySQL 有没有在跑（没跑就自动拉起），然后用 `sv_user` 进入 `video_fastqpi` 库。

也可以在终端里：

```powershell
cd D:\video_fastqpi
.\mysql-cli.bat          # 纯批处理，双击或命令行都能跑
```

> `.ps1` 脚本需要先设执行策略、不能双击；日常用 `.bat` 更省事（`mysql-cli.bat`、`start-all.bat`、`stop-all.bat` 都是为此准备的）。

进去后是标准的 MySQL 提示符，常用命令：

```sql
SHOW DATABASES;                 -- 看有哪些库
SHOW TABLES;                    -- 看 video_fastqpi 里有哪些表
SELECT id, username, avatar IS NOT NULL AS has_avatar FROM users;   -- 看用户
SELECT id, title, views, likes FROM videos;                          -- 看视频
exit;                           -- 退出（或按 Ctrl+C）
```

手动进入（不用脚本）——绿色版 MySQL 没注册成服务，所以要用**绝对路径**调客户端：

```powershell
& "D:\video_fastqpi\mysql\mysql-8.0.28-winx64\bin\mysql.exe" -u sv_user -p -D video_fastqpi
# 回车后按提示输入密码（即 backend/.env 里的 DB_PASSWORD）
```

- 应用账号：`sv_user` / 密码见 `backend/.env` 的 `DB_PASSWORD`
- root 账号：**空密码**（`-u root` 后直接回车；用 bat 时可先把末尾 `-u sv_user -D video_fastqpi` 改成 `-u root`）
- 只监听 `127.0.0.1:3306`，**仅本机可连**

### 用图形化工具（Navicat / DBeaver / MySQL Workbench）

新建连接，填：主机 `127.0.0.1`、端口 `3306`、用户 `sv_user`、密码见 `backend/.env` 的 `DB_PASSWORD`、库 `video_fastqpi`。

### 库中的表

| 表 | 说明 |
|---|---|
| `users` | 用户（含 `avatar`、`bio`、`wechat_openid`） |
| `videos` | 视频 |
| `likes` | 点赞 |
| `favorites` | 收藏 |
| `follows` | 关注关系 |
| `video_embeddings` | 视频向量（AI 检索用，float32 BLOB） |
| `chat_messages` | AI 对话历史 |
| `wx_login_states` | 微信扫码登录状态 |

### 方式 B：使用你自己的 MySQL

```sql
CREATE DATABASE video_fastqpi DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

然后修改 `backend/.env` 里的 `DB_HOST / DB_PORT / DB_USER / DB_PASSWORD` 即可。
若不想用 MySQL，也可用 `DATABASE_URL_OVERRIDE` 直接指定任意 SQLAlchemy 连接串（如 SQLite）。

> 已有旧库时，运行一次 `python migrate.py` 即可补上本次新增的 `users.bio`、`users.wechat_openid` 列与 `follows`、`wx_login_states` 表。

## 二、启动后端

```powershell
cd D:\video_fastqpi\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# .env 已生成好（指向内置 MySQL 的 sv_user）
uvicorn app.main:app --reload --port 8000
```

- 首次启动会自动建表并创建 `uploads/` 目录
- 接口文档：http://127.0.0.1:8000/docs

## 三、启动前端

```powershell
cd D:\video_fastqpi\frontend
npm install
npm run dev
```

打开 http://localhost:5173 （Vite 已配置 `/api` 与 `/media` 代理到 8000 端口）

---

## 四、主要接口

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/auth/register` | 注册（返回 token） |
| POST | `/api/auth/login` | 登录（JSON） |
| POST | `/api/auth/token` | 登录（表单，供 Swagger） |
| GET | `/api/auth/me` | 当前用户 |
| PATCH | `/api/auth/avatar` | 设置预设头像（传 data URL） |
| POST | `/api/auth/avatar` | 上传自定义头像（multipart，≤5MB） |
| GET | `/api/auth/wx/qrcode` | 微信扫码：生成二维码 + state |
| GET | `/api/auth/wx/poll?state=` | 微信扫码：轮询状态（成功返回 token） |
| GET | `/api/auth/wx/virtual` | 一键虚拟扫码登录（演示用） |
| GET | `/api/auth/wx/callback` | 微信授权回调（真实模式） |
| GET | `/api/users/{id}` | 用户资料（粉丝/关注/作品/获赞/播放） |
| PATCH | `/api/users/me` | 改昵称 / 个性签名 |
| POST | `/api/users/{id}/follow` | 关注 / 取关 |
| GET | `/api/users/{id}/videos` | 该用户作品 |
| GET | `/api/users/{id}/likes` | 该用户点赞的视频 |
| GET | `/api/users/{id}/favorites` | 该用户收藏的视频 |
| POST | `/api/videos` | 上传视频（multipart） |
| GET | `/api/videos` | 列表（`q`/`sort`/`page`/`owner_id`） |
| GET | `/api/videos/{id}` | 详情（播放数 +1） |
| PATCH | `/api/videos/{id}` | 修改标题/描述（仅作者） |
| DELETE | `/api/videos/{id}` | 删除（仅作者） |
| POST | `/api/videos/{id}/like` | 点赞/取消 |
| POST | `/api/videos/{id}/favorite` | 收藏/取消 |
| POST | `/api/videos/{id}/share` | 转发计数 |
| GET | `/api/videos/favorites/me` | 我的收藏 |

### AI 助手

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/ai/status` | 是否启用 + 已索引视频数 |
| POST | `/api/ai/chat` | 提问（`question` + 可选 `session_key`）→ 答案 + 引用来源 |
| GET | `/api/ai/history/{session_key}` | 拉取历史 |
| DELETE | `/api/ai/history/{session_key}` | 清空历史 |
| POST | `/api/ai/reindex?force=true` | 重建 / 补齐视频向量索引 |

---

## 五、微信扫码登录 & 头像 & 关注

### 微信扫码登录

- **真实模式**：在 `backend/.env` 填入 `WECHAT_APP_ID` / `WECHAT_APP_SECRET`（微信开放平台「网站应用」），并把 `WECHAT_REDIRECT_URI` 配成开放平台后台登记的回调地址。
- **Mock 模式（默认）**：不填 AppID 时自动启用。二维码指向本机 `/api/auth/wx/mock?state=...` 模拟授权页，点「确认登录」即完成，全程离线、可演示。
- 前端入口：顶栏「微信登录」按钮、登录页「微信扫码登录」按钮。打开弹窗后会轮询 `/api/auth/wx/poll`，成功后自动写入 token 并跳转首页。

### 头像

- 新用户（含微信登录）自动生成一张渐变默认头像（Pillow 本地绘制，中文首字也能正常渲染）。
- **注册页**即可选择预设头像（8 款霓虹头像，不选则用昵称首字默认头像）。
- 个人主页点头像 → 弹「更换头像」：8 款预设霓虹头像（纯内联 SVG）或上传自己的图片（≤5MB）。
- 全站统一使用 `Avatar` 组件（顶栏、视频卡片、播放页、悬停卡一致）。
- 登录后顶栏**只显示头像、不显示昵称**；鼠标悬停时头像放大并弹出个人信息卡（粉丝/关注/作品/获赞 + 签名 + 快捷入口 + 退出）。

### 关注 & 悬停名片（B 站式）

- 鼠标悬停在任意用户名 / 头像上 → 弹出资料卡：头像、签名、粉丝/关注/作品/获赞，并可直接「关注 / 已关注」。
- 个人主页（`/user/:id`）有「作品 / 点赞 / 收藏」三个 Tab，自己可「编辑资料」（昵称 + 签名）。

---

## 六、AI 助手（方案二：手写轻量 RAG）

为什么不用向量数据库？站内数据量在几百条以内，把「标题 + 简介」向量化后**在进程内暴力算余弦相似度**就够了，
不引入 Chroma / Milvus / pgvector 这类额外服务，省一个要维护的组件。

**链路**

1. 每个视频把 `标题 + 作者 + 简介` 拼成文本 → `text-embedding-v3` 得到 1024 维向量 → 以 float32 原始字节存入
   MySQL 的 `video_embeddings.vector`（BLOB）。
2. 提问时把问题也向量化，对所有视频向量算余弦相似度，取 Top-K（默认 3）。
3. Top-K 拼进 system prompt，连同最近 6 条历史交给 `qwen-plus` 生成答案。
4. 回答带 `sources`（命中的视频 id/标题/相似度），前端渲染成可点击的引用小胶囊。
5. 会话记录存入 `chat_messages`，`session_key` 存在浏览器 localStorage，刷新不丢。

**触发点**：右下角悬浮「✦」按钮，随时可聊；视频详情页还有「✦ 问问 AI」按钮，自动带上当前视频上下文。

**配置**（`backend/.env`）

```ini
DASHSCOPE_API_KEY=sk-xxx          # 百炼控制台申请
AI_CHAT_MODEL=qwen-plus
AI_EMBED_MODEL=text-embedding-v3
AI_EMBED_DIM=1024
AI_TOP_K=3
```

> Key 没配也能跑：`/api/ai/status` 返回 `enabled:false`，前端自动隐藏 AI 入口，其余功能不受影响。
> 上传新视频后会自动在后台补索引；也可手动 `POST /api/ai/reindex?force=true`。

---

## 七、生产部署建议

1. **前端**：`npm run build` 生成 `dist/`，交给 Nginx 托管，并把 `/api`、`/media` 反向代理到后端。
2. **后端**：`uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4`（或用 gunicorn + uvicorn worker）。
3. **大文件上传**：Nginx 需放宽 `client_max_body_size`（如 `client_max_body_size 1024m;`）。
4. **迁移**：当前用 `create_all` 自动建表；正式项目建议接入 Alembic。
5. **安全**：务必替换 `SECRET_KEY`；生产环境限制 `CORS_ORIGINS`。

---

## 八、注意事项

- 视频转码 / 切片 / CDN 未包含（保持“更简单”的定位）；直接原样播放。
- 转发为简化实现（计数 + 前端 Web Share / 复制链接）。
- 单文件上限由 `.env` 的 `MAX_VIDEO_MB` 控制（默认 1024MB）；头像上限 `MAX_AVATAR_MB`（默认 5MB）。
- AI 依赖外部百炼接口，离线环境不可用；embedding 是网络调用，首次启动会在后台补齐现有视频的向量。
- 微信登录未配置 AppID 时为 Mock，仅用于本地/演示；上线需接入真实网站应用。

---

## 九、自测

```powershell
cd D:\video_fastqpi\backend
.\\.venv\\Scripts\\python.exe smoke_test.py    # 离线冒烟（SQLite 临时库）29 项
.\\.venv\\Scripts\\python.exe live_e2e.py      # 真实 MySQL 端到端（需后端已启动）9 项
.\\.venv\\Scripts\\python.exe ai_smoke.py      # AI 助手链路（需后端 + DASHSCOPE_API_KEY）
.\\.venv\\Scripts\\python.exe wx_smoke.py      # 微信登录 / 头像 / 关注（需后端已启动）41 项
```

> 本机验证结果：离线 29/29 通过，真实 MySQL 9/9 通过，微信扫码/头像/关注 41/41 通过，前端 `npm run build` 构建成功。
