# 后端代码阅读路线图

> 面向第一次接触本项目的人。按下面的顺序读，从"应用怎么起来"到"接口怎么写"，逻辑是逐层展开的。

---

## 一、先看全局：三层结构

```
请求 → 路由层(routers/)  →  数据访问层(database + models)  →  MySQL
              ↓
         校验层(schemas) / 认证(security + deps) / 序列化(services)
              ↑
         配置(config) —— 所有层都在用
```

**一句话理解各文件职责：**

| 文件 | 职责 | 类比 |
|---|---|---|
| `config.py` | 读 .env，暴露配置对象 | 总控开关 |
| `database.py` | 建连接池、发 Session | 数据库水管 |
| `models.py` | 定义表结构（ORM） | 数据库的表 |
| `schemas.py` | 定义接口进出参长什么样 | 接口契约 |
| `security.py` | 密码加密、签发/校验 JWT | 门禁系统 |
| `deps.py` | "当前登录用户是谁" | 安检员 |
| `services.py` | 把 DB 对象拼成前端要的 JSON | 包装工 |
| `routers/*.py` | 具体接口（增删改查） | 前台窗口 |
| `main.py` | 组装以上一切并启动 | 总装配 |

---

## 二、推荐阅读顺序（9 步）

### 第 1 步 · `app/main.py`（31 行）
**先看这个能知道"程序从哪开始"。**
重点：
- `settings.upload_path.mkdir(...)` —— 为什么在挂载前建目录（StaticFiles 实例化即校验路径）
- `lifespan` —— 启动时 `create_all` 自动建表
- `include_router(auth/videos)` —— 路由在这里注册
- `app.mount("/media", ...)` —— 视频文件走静态服务

### 第 2 步 · `app/config.py`（39 行）
**所有配置的来源。**
重点：`Settings` 类字段 ↔ `.env` 键的对应关系；`database_url` 属性怎么拼出连接串；`upload_path` 怎么把相对路径变成绝对路径。

### 第 3 步 · `app/database.py`（20 行）
**连接怎么建。**
重点：`create_engine(pool_pre_ping=True)` 防止连接失效；`SessionLocal` 是会话工厂；`get_db()` 是 FastAPI 依赖，请求结束自动 close；`Base` 是模型基类。

### 第 4 步 · `app/models.py`（58 行）
**四个表 + 它们的关系。**
- `User` 1—N `Video`（`owner_id` 外键）
- `Video` 1—N `Like` / `Favorite`（级联删除）
- `Like` / `Favorite` 都有 `UniqueConstraint(user_id, video_id)` —— 保证一人只能赞一次
- `BigIntPK = BigInteger().with_variant(Integer, "sqlite")` —— 为了 SQLite 也能自增
- 最后一行 `Index(...)` —— 按作者+时间查询的联合索引

### 第 5 步 · `app/schemas.py`（50 行）
**接口的"形状"。**
`UserOut` / `VideoOut` 是响应体，注意 `VideoOut` 里 `likes/favorites/shares/liked/favorited/url` 这些**不是数据库字段**，是算出来的（下一步会看到）。
`PageOut` 是分页壳子，`ActionOut` 是点赞/收藏的返回。

### 第 6 步 · `app/security.py`（22 行）
**密码和令牌。**
`hash_password` / `verify_password` 用 bcrypt；`create_access_token` 把 user id 塞进 `sub` 并设过期；`decode_token` 失败返回 None（不抛异常）。

### 第 7 步 · `app/deps.py`（34 行）
**"当前用户是谁"的唯一出口。**
- `get_current_user`：没 token / token 无效 → 401
- `get_current_user_optional`：没登录返回 None（用于列表页，登录与否都能看）

> 这两个函数在路由里用 `Depends(...)` 注入，是理解接口鉴权的关键。

### 第 8 步 · `app/services.py`（47 行）
**seralize_video：DB 对象 → 前端 JSON。**
解答了第 5 步的疑问：点赞数、收藏数、当前用户是否已赞/已藏，全在这里用 SQL 聚合查出来拼进去。

### 第 9 步 · `app/routers/`（重点，两个文件）
- **`auth.py`（47 行）**：注册 / 登录(JSON) / 登录(表单，给 Swagger) / 我
- **`videos.py`（230 行，核心）**：按顺序读——
  1. `upload_video`：分块读文件 + 大小限制 + 存盘 + 可选封面
  2. `my_favorites`：⚠️ 注意它写在 `/{video_id}` **之前**，否则 "favorites" 会被当成 id
  3. `list_videos`：搜索 / 排序(new|hot) / 分页 / 按作者
  4. `get_video`：详情 + 播放数 +1
  5. `update_video` / `delete_video`：都校验 `owner_id != user.id → 403`
  6. `toggle_like` / `toggle_favorite`：存在就删、不存在就加（幂等切换）
  7. `share_video`：简化实现，直接给 views +1

---

## 三、想动手验证？

```powershell
# 离线冒烟（不需要 MySQL，用 SQLite）
cd D:\video_fastqpi\backend
.\.venv\Scripts\python.exe smoke_test.py

# 真实 MySQL 端到端（需后端已启动）
.\.venv\Scripts\python.exe live_e2e.py
```

边读 `routers/` 边对照这两个测试文件，每个接口的预期行为一目了然。

---

## 四、一个请求的完整链路（例子：点赞）

```
前端 POST /api/videos/3/like  (Authorization: Bearer <token>)
  → main.py 交给 videos.router
  → Depends(get_current_user) 解出用户 (deps.py → security.decode_token)
  → toggle_like() 查 likes 表，有则删、无则加
  → 返回 ActionOut { active, count }
```

---

## 五、可读性标记说明

- 依赖注入一律用 `Depends(...)`，参数名即语义（`db` = 会话，`user` = 当前用户）
- 所有"只有作者能做"的操作都返回 403，未登录返回 401
- 表名复数小写（users/videos/likes/favorites），字段蛇形命名

---

## 六、AI 助手模块（新增，建议最后读）

新增两个文件 + 改动三处：

```
app/ai_service.py       # 核心：向量化 + 检索 + 对话（7592 字节）
app/routers/ai.py       # 5 个接口：status / chat / history / clear / reindex
```

改动：`models.py`（+video_embeddings、chat_messages 两张表）、`schemas.py`（+ChatIn/ChatOut/SourceOut/HistoryOut/StatusOut）、`main.py`（注册 ai.router，共 24 条路由）、`routers/videos.py`（上传成功后调 `ai_service.index_new_video_bg()`）。

阅读顺序：

1. `models.py` 看 `VideoEmbedding`（vector 存 float32 原始字节的 BLOB）与 `ChatMessage`。
2. `ai_service.py`：`embed()` → 向量；`_pack/_unpack()` float32↔bytes；`refresh_embeddings()` 补齐索引；`search_videos()` 手写余弦（`zip` + 点乘 + 范数）；`build_prompt()` 拼 system；`chat()` 串流程。
3. `routers/ai.py`：`/chat` 拿 `session_key`（默认 `anon`）落库 + 返回 `sources`。
4. 前端 `components/AiChat.jsx`：悬浮球 + 面板 + 打字机；监听 `window` 的 `ai-ask` 事件（视频页「问问 AI」按钮触发）。

**一句话看懂**：没有向量库，把向量当二进制块存 MySQL，检索时全拉到内存里算余弦——数据量小就这么省事。
