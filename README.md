# SurrealKB · 企业知识库问答站

把你手头的 PDF / Word / TXT / Markdown 文档丢进来，变成一个**能对话、带原文出处**的知识库。
多用户 + 多知识库（团队）隔离，AI 助手基于你知识库里的文档作答并标注来源。

- 后端：**FastAPI** + SQLAlchemy 2.0 + JWT
- 前端：**React 18** + Vite + React Router
- 数据库：**MySQL 8**（utf8mb4）
- 登录：账号密码 **+ 微信扫码登录**（未配置 AppID 时自动降级为本地 Mock 扫码）
- 知识库：一个账号可**创建**自己的知识库，或用**邀请码加入**团队知识库（租户隔离）
- 文档：PDF（PyMuPDF 提取）/ Word（python-docx）/ TXT / Markdown，自动解析 → 分块 → 向量化
- AI：**阿里云百炼（DashScope）** `qwen-plus` + `text-embedding-v3`，手写轻量 RAG（向量 + BM25 混合检索，无外部向量库）
- 视觉：超现实霓虹风（纯手写 CSS，无 UI 框架）
- 存储：本地 `backend/uploads`，通过 `/media/*` 静态服务

> 本项目的应用名是 **SurrealKB**，目录名 `surreal_kb`，数据库名 `video_fastqpi`（沿用建库时的名字，未改动以免动数据）。

---

## 目录结构

```
surreal_kb/
├─ backend/
│  ├─ app/
│  │  ├─ main.py           # FastAPI 入口（挂载 5 个路由 + /media 静态）
│  │  ├─ config.py         # 配置（读 .env）
│  │  ├─ database.py       # 引擎 / 会话
│  │  ├─ models.py         # Tenant / User / Document / Chunk / Follow / WxLoginState / ChatMessage
│  │  ├─ schemas.py        # Pydantic 请求 / 响应模型
│  │  ├─ security.py       # bcrypt + JWT
│  │  ├─ deps.py           # 依赖（当前用户）
│  │  ├─ doc_service.py    # 文档文本提取（PDF/DOCX/TXT/MD）+ 语义分块
│  │  ├─ ai_service.py     # AI 助手：向量索引 + 混合检索 + 对话
│  │  ├─ wechat_service.py # 微信扫码登录（真实 + 本地 Mock）+ 生成默认头像
│  │  └─ routers/
│  │     ├─ auth.py        # 注册 / 登录 / 我 / 头像 / 微信扫码
│  │     ├─ tenants.py     # 知识库：当前 / 创建 / 加入 / 成员 / 邀请码
│  │     ├─ users.py       # 用户资料 / 关注
│  │     ├─ documents.py   # 文档上传 / 列表 / 详情 / 分块 / 改名 / 删除 / 重建索引
│  │     └─ ai.py          # AI 问答 / 历史 / 重建索引
│  ├─ migrate.py           # 轻量迁移（给已有库补新列 / 新表，幂等）
│  ├─ sql/init.sql         # 建库脚本
│  ├─ requirements.txt
│  └─ .env.example
└─ frontend/
   ├─ src/
   │  ├─ App.jsx  main.jsx  store.jsx  api.js  styles.css  presets.js
   │  ├─ components/  (Navbar / DocCard / AiChat / Avatar / AvatarPicker / UserHoverCard / EditProfile / WechatLogin / AccountMenu / PresetGrid / Background / format)
   │  └─ pages/       (Home / DocDetail / Upload / Login / Register / Profile / Team)
   ├─ index.html
   └─ package.json
```

---

## 一、准备 MySQL

本项目已内置一套**免安装（绿色版）MySQL 8.0**，无需管理员权限，开箱即用。

### 方式 A：使用内置 MySQL（推荐）

```powershell
cd D:\surreal_kb
.\start-mysql.ps1     # 启动（后台运行，监听 127.0.0.1:3306）
.\stop-mysql.ps1      # 停止
```

> **一键启停脚本**（本机便捷脚本，不入库）：
> - 全部启停：`start-all.bat` / `stop-all.bat`
> - 只启停后端：`start-backend.bat` / `stop-backend.bat`
> - 只启停前端：`start-frontend.bat` / `stop-frontend.bat`
> - 进入数据库：`mysql-cli.bat`
>
> 这些 `.bat` / `.ps1` 均为**纯 ASCII、双击即用**；根目录下的脚本已全部在 `.gitignore` 中忽略（含本机绝对路径 / 本地口令，随机器不同，不适合提交）。

已自动完成：
- 解压至 `D:\surreal_kb\mysql\mysql-8.0.28-winx64`
- 数据目录 `D:\surreal_kb\mysql_data`（已初始化）
- 建库 `video_fastqpi`（utf8mb4，库名沿用早期，不影响使用）
- 专用账号：`sv_user` / 密码见 `backend/.env` 的 `DB_PASSWORD`（已授予该库全部权限）

### 进入数据库（命令行）

**双击即用**：直接**双击** `D:\surreal_kb\mysql-cli.bat` —— 它会先检查 MySQL 有没有在跑（没跑就自动拉起），然后用 `sv_user` 进入 `video_fastqpi` 库。

也可以在终端里：

```powershell
cd D:\surreal_kb
.\mysql-cli.bat          # 纯批处理，双击或命令行都能跑
```

> `.ps1` 脚本需要先设执行策略、不能双击；日常用 `.bat` 更省事。

进去后是标准的 MySQL 提示符，常用命令：

```sql
SHOW DATABASES;                 -- 看有哪些库
SHOW TABLES;                    -- 看库里有哪些表
SELECT id, username, tenant_id, role FROM users;   -- 看用户与其知识库
SELECT id, title, status, chunk_count FROM documents;  -- 看文档
exit;                           -- 退出（或按 Ctrl+C）
```

手动进入（不用脚本）——绿色版 MySQL 没注册成服务，所以要用**绝对路径**调客户端：

```powershell
& "D:\surreal_kb\mysql\mysql-8.0.28-winx64\bin\mysql.exe" -u sv_user -p -D video_fastqpi
# 回车后按提示输入密码（即 backend/.env 里的 DB_PASSWORD）
```

- 应用账号：`sv_user` / 密码见 `backend/.env` 的 `DB_PASSWORD`
- root 账号：**空密码**（`-u root` 后直接回车）
- 只监听 `127.0.0.1:3306`，**仅本机可连**

### 用图形化工具（Navicat / DBeaver / HeidiSQL / MySQL Workbench）

新建连接，填：主机 `127.0.0.1`、端口 `3306`、用户 `sv_user`、密码见 `backend/.env` 的 `DB_PASSWORD`、库 `video_fastqpi`。

### 库中的表

| 表 | 说明 |
|---|---|
| `tenants` | 知识库（租户）：名称 / slug / 邀请码 |
| `users` | 用户（含 `avatar`、`bio`、`wechat_openid`、`tenant_id`、`role`） |
| `documents` | 文档（类型 / 体积 / 状态 / 分块数 / 字数 / 上传者） |
| `chunks` | 文档分块 + 向量（AI 检索单元，float32 BLOB） |
| `follows` | 关注关系（保留自早期社交功能） |
| `wx_login_states` | 微信扫码登录状态 |
| `chat_messages` | AI 对话历史（按 tenant/user 归属） |

> 早期视频站版本的 `videos / likes / favorites / video_embeddings` 表已从代码中移除（库中若仍在，属历史遗留，不影响运行）。

### 方式 B：使用你自己的 MySQL

```sql
CREATE DATABASE video_fastqpi DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

然后修改 `backend/.env` 里的 `DB_HOST / DB_PORT / DB_USER / DB_PASSWORD` 即可。
若不想用 MySQL，也可用 `DATABASE_URL_OVERRIDE` 直接指定任意 SQLAlchemy 连接串（如 SQLite）。

> 已有旧库时，运行一次 `python migrate.py` 即可补上新增的 `users.tenant_id`、`users.role`、`chat_messages.tenant_id` 列与 `tenants` 表，并为存量用户各建一个默认知识库。

## 二、启动后端

```powershell
cd D:\surreal_kb\backend
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
cd D:\surreal_kb\frontend
npm install
npm run dev
```

打开 **http://localhost:5173** （Vite 已配置 `/api` 与 `/media` 代理到 8000 端口）

> ⚠️ 用 `localhost` 而不是 `127.0.0.1`：Vite 开发服务器绑定在 IPv6 `::1` 上，用 `127.0.0.1:5173` 可能打不开。

---

## 四、主要接口

### 认证 / 头像 / 微信

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/auth/register` | 注册（可带 `tenant_name` 建库 / `invite_code` 加入 / `avatar` 预设头像） |
| POST | `/api/auth/login` | 登录（JSON） |
| POST | `/api/auth/token` | 登录（表单，供 Swagger） |
| GET | `/api/auth/me` | 当前用户 |
| PATCH | `/api/auth/avatar` | 设置头像（预设 data URL） |
| POST | `/api/auth/avatar` | 上传自定义头像（multipart，≤5MB） |
| GET | `/api/auth/wx/qrcode` | 微信扫码：生成二维码 + state |
| GET | `/api/auth/wx/poll?state=` | 微信扫码：轮询状态（成功返回 token） |
| GET | `/api/auth/wx/virtual` | 一键虚拟扫码登录（演示用） |
| GET | `/api/auth/wx/callback` | 微信授权回调（真实模式） |

### 知识库（租户）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/tenants/current` | 当前知识库信息（含成员数 / 文档数；邀请码仅 owner/admin 可见） |
| POST | `/api/tenants` | 创建知识库（当前用户设为 owner） |
| POST | `/api/tenants/join` | 凭邀请码加入 |
| POST | `/api/tenants/invite/reset` | 重置邀请码（仅 owner/admin，旧码立即失效） |
| GET | `/api/tenants/members` | 成员列表 |
| GET | `/api/tenants/members/detail` | 成员明细（含角色） |

### 文档

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/documents` | 上传文档（multipart，≤50MB，自动解析 + 分块）。同名默认报 409；带 `overwrite=true` 则覆盖旧文档 |
| GET | `/api/documents` | 列表（`q`/`status`/`owner_id`/`page`/`page_size`） |
| GET | `/api/documents/{id}` | 详情（含 `revision` 版本号） |
| GET | `/api/documents/{id}/content` | 提取出的纯文本全文（「原文」阅读视图） |
| GET | `/api/documents/{id}/raw` | 下载/预览原始上传文件（PDF 可内嵌） |
| GET | `/api/documents/{id}/chunks` | 该文档全部分块（AI 检索单元） |
| PUT | `/api/documents/{id}` | 在线编辑正文（存历史快照 → 重建分块与向量） |
| GET | `/api/documents/{id}/revisions` | 历史版本列表 |
| GET | `/api/documents/{id}/revisions/{rev_id}` | 查看某历史版本全文 |
| POST | `/api/documents/{id}/revisions/{rev_id}/restore` | 回滚到某历史版本 |
| PATCH | `/api/documents/{id}` | 改标题 |
| DELETE | `/api/documents/{id}` | 删除（上传者或管理员） |
| POST | `/api/documents/{id}/reindex` | 重新解析并重建向量索引 |

### 用户

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/users/{id}` | 资料（粉丝/关注/文档数） |
| PATCH | `/api/users/me` | 改昵称 / 个性签名 |
| POST | `/api/users/{id}/follow` | 关注 / 取关 |

### AI 助手

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/ai/status` | 是否启用 + 已索引分块数 |
| POST | `/api/ai/chat` | 提问（`question` + 可选 `session_key`）→ 答案 + 出处 |
| GET | `/api/ai/history/{session_key}` | 拉取历史 |
| DELETE | `/api/ai/history/{session_key}` | 清空历史 |
| POST | `/api/ai/reindex?force=true` | 重建 / 补齐当前知识库的分块向量 |

---

## 五、产品功能

### 知识库（多租户）

- 注册时可选：**创建自己的知识库**（`tenant_name`）或用**邀请码加入**团队知识库；都不填则暂时无库，登录后在「知识库」页创建或加入。
- 每个知识库有唯一**邀请码**；**仅创建者 / 管理员（owner/admin）可见、可复制、可重置**，普通成员看不到邀请码（避免任意成员拉人）。
- 「重置邀请码」后旧码立即失效，已分享出去的码无法再加入，需重新分享新码。
- **租户隔离**：文档、分块、AI 检索全部限定在当前用户所属知识库内，看不到别的库。
- 角色：`owner`（建库者）/ `admin`（管理员）/ `member`（成员）。删除文档时上传者或 owner/admin 可删。
- **一个用户同一时间只属于一个知识库**（`user.tenant_id` 单值）；加入时若已有库会提示。

### 文档（上传 → 解析 → 分块）

- 支持 **PDF / Word(.docx) / TXT / Markdown**，单个 ≤ `MAX_DOC_MB`（默认 50MB）。
- 上传后同步解析提取文本 → 语义分块（默认 800 字/块、重叠 120 字）→ 后台补向量。
- 首页文档列表支持**关键词搜索**、**按状态筛选**（全部 / 已就绪 / 处理中 / 失败）、分页。
- 文档详情页可查看**原文样式/纯文本/分块**三种视图、改名、**在线编辑正文**（存历史版本可回滚）、**重建索引**、删除，并可「**问问 AI**」总结该文档。

### AI 助手（对话式问答，带出处）

- 右下角悬浮「✦」按钮随时可聊；文档详情页「问问 AI」会把当前文档带进上下文。
- 回答严格基于**你知识库里的文档**，句末标注来源编号 `[1]`，前端渲染成可点击的引用胶囊。
- 会话记录按 `session_key` 保存（存 localStorage），刷新不丢。

---

## 六、AI 助手实现（手写轻量 RAG）

为什么不用向量数据库？站内文档量在几千分块以内，把分块向量化后**在进程内暴力算相似度**就够了，
不引入 Chroma / Milvus / pgvector 这类额外服务，省一个要维护的组件。

**索引链路**

1. 文档解析后切成 Chunk（带 `tenant_id`），`text-embedding-v3` 把每块转成 1024 维向量，
   以 float32 原始字节存入 `chunks.vector`（MySQL BLOB）。
2. 上传即后台补索引；也可手动 `POST /api/ai/reindex?force=true`。

**检索链路（混合检索）**

3. 提问时：**向量相似度（权重 0.55）** + **BM25 关键词分（权重 0.45）**，各自 min-max 归一后加权融合；
   只在当前租户的 Chunk 内检索，取 Top-K（`AI_TOP_K`，默认 4）。
   - 加 BM25 的原因：纯向量对「人名 / 编号 / 具体字段」这类关键词查询不敏感。
   - 中文分词用「字符二元组 + 英文/数字词」，无需第三方分词库。
4. Top-K 片段拼进 system prompt，连同最近 6 条历史交给 `qwen-plus` 生成答案，并回带 `sources`。

**配置**（`backend/.env`）

```ini
DASHSCOPE_API_KEY=sk-xxx          # 百炼控制台申请
AI_CHAT_MODEL=qwen-plus
AI_EMBED_MODEL=text-embedding-v3
AI_EMBED_DIM=1024
AI_TOP_K=4
```

> Key 没配也能跑：`/api/ai/status` 返回 `enabled:false`，前端自动隐藏 AI 入口，其余功能不受影响。
>
> 注意：索引刷新用了**进程内锁**串行化（启动补索引 / 上传自动索引 / 手动重建），多 worker 部署时需换 DB 层锁或独立索引 worker。

---

## 七、技术要点（阅读代码前值得知道）

- **文档提取**：PDF 优先用 PyMuPDF 的排版顺序模式（`sort=True`），能把表单里与标签分离的填写值贴回标签后（pypdf 会把值抛到文末导致丢失）；DOCX 按 body 真实顺序遍历「段落 + 表格」交错结构，避免顺序错乱。
- **分块**：按语义单元聚合到 ~`chunk_size`，块间按**整句**重叠；重叠长度**硬性封顶**，避免词汇表这类「无句末标点」文本滚雪球式重复。仅 PDF 做「合并视觉折行」，其他格式保留原段落/行结构。
- **向量存储**：`struct.pack("<{n}f", *vec)` 把向量打包成小端 float32 字节串，存 BLOB；`_unpack` 逆向还原。
- **门禁**：`deps.get_current_user` 未登录 401；`get_current_user_optional` 游客返回 None（列表页可游客浏览）。
- **路由顺序坑**：静态路径（如 `/api/users/me`）必须写在动态路径（`/{user_id}`）之前。

---

## 八、生产部署建议

1. **前端**：`npm run build` 生成 `dist/`，交给 Nginx 托管，并把 `/api`、`/media` 反向代理到后端。
2. **后端**：`uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4`（或用 gunicorn + uvicorn worker）。
3. **大文件上传**：Nginx 需放宽 `client_max_body_size`（如 `client_max_body_size 64m;`）。
4. **迁移**：当前用 `create_all` + `migrate.py`；正式项目建议接入 Alembic。
5. **安全**：务必替换 `SECRET_KEY`；生产环境限制 `CORS_ORIGINS`；为 `sv_user` 设置强密码。
6. **多 worker 注意**：AI 索引用的进程内锁在多 worker 下失效，需改用 DB 层锁或独立索引进程。

---

## 九、注意事项

- **扫描版 PDF**（图片型）无法提取文字，会被标记 `failed`（`error` 提示「未能提取到文本」）。
- 文档**支持「原文样式」预览**：Word（mammoth 转 HTML，保留标题/列表/表格/加粗）、Markdown（轻量渲染）、PDF（iframe 内嵌）、TXT（等宽）；详情页还有纯文本与分块视图。
- 转发 / 评论 / 弹幕等功能未包含（保持「更简单」的定位）。
- AI 依赖外部百炼接口，离线环境不可用；embedding 是网络调用，首次启动会在后台补齐现有文档的向量。
- 微信登录未配置 AppID 时为 Mock，仅用于本地/演示；上线需接入真实网站应用。`/api/auth/wx/virtual` 是演示后门，**生产环境应移除或加保护**。

---

## 十、关于版本控制（提交 GitHub 前必读）

根目录 `.gitignore` 已配好，以下内容**不会**被提交：

| 类别 | 例子 | 原因 |
|---|---|---|
| 密钥 / 环境变量 | `backend/.env`、`.env.*` | 含真实密钥（仅保留 `.env.example`） |
| 本地 MySQL | `mysql/`、`mysql_data/` | 体积巨大（数百 MB） |
| 依赖 / 构建 | `.venv/`、`node_modules/`、`frontend/dist/` | 可重建 |
| 用户上传 | `backend/uploads/*` | 体积大 + 含隐私 |
| 本机启停脚本 | 根目录 `*.bat` / `*.ps1` / `*.cmd` | 含本机绝对路径 / 本地口令 |
| 临时 / 调试 | `backend/_*.py`、`*.log`、`*.err`、`*.zip`、`dbg_report*.txt` | 一次性产物 |
| 编辑器 | `.vscode/`、`.idea/` | 个人配置 |

追踪前自检：

```powershell
git status --short          # 看有没有该忽略的冒出来
git check-ignore -v <文件>   # 查某个文件被哪条规则忽略
```

---

## 十一、自测

```powershell
cd D:\surreal_kb\backend
.\.venv\Scripts\python.exe smoke_test.py    # 离线冒烟（SQLite 临时库）
.\.venv\Scripts\python.exe kb_smoke.py      # 知识库全链路（真实 MySQL + 真实百炼 API）
.\.venv\Scripts\python.exe ai_smoke.py      # AI 助手链路（需后端 + DASHSCOPE_API_KEY）
.\.venv\Scripts\python.exe wx_smoke.py      # 微信登录 / 头像 / 关注（需后端已启动）
.\.venv\Scripts\python.exe live_e2e.py      # 真实 MySQL 端到端（需后端已启动）
```

> 本机验证结果：知识库全链路（注册建库 → 上传 → 分块 → 问答带出处 → 越权隔离）通过，微信扫码/头像/关注通过，前端 `npm run build` 构建成功。
