# 后端代码阅读路线图

> 面向第一次接触本项目的人。按下面的顺序读，从「应用怎么起来」到「接口怎么写」，逻辑逐层展开。

---

## 一、先看全局：分层结构

```
请求 →  路由层(routers/)  →  数据访问层(database + models)  →  MySQL
             ↓
        校验层(schemas) / 认证(security + deps)
             ↓
        业务服务层(doc_service 文档解析分块 / ai_service RAG / wechat_service 微信)
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
| `deps.py` | 「当前登录用户是谁」 | 安检员 |
| `doc_service.py` | 文档文本提取 + 语义分块 | 资料整理员 |
| `ai_service.py` | 向量化 + 混合检索 + 对话（RAG） | 智能问答大脑 |
| `wechat_service.py` | 微信扫码登录 + 生成默认头像 | 外部登录对接 |
| `routers/*.py` | 具体接口（增删改查） | 前台窗口 |
| `main.py` | 组装以上一切并启动 | 总装配 |

---

## 二、推荐阅读顺序（11 步）

### 第 1 步 · `app/main.py`（60 行）
**先看这个能知道「程序从哪开始」。**
重点：
- `settings.upload_path.mkdir(...)` / `pkgs avatars/docs` —— 为什么必须在 mount 之前建目录（StaticFiles 实例化即校验路径）
- `lifespan` —— 启动时 `create_all` 自动建表；`ai_enabled` 时开后台线程补向量索引
- `include_router(auth / tenants / users / documents / ai)` —— 5 个路由在此注册
- `app.mount("/media", ...)` —— 头像等静态文件服务
- `/api/health` —— 探活

### 第 2 步 · `app/config.py`（78 行）
**所有配置的来源。**
重点：`Settings` 类字段 ↔ `.env` 键的对应关系（环境变量优先级高于默认值、大小写不敏感）；
`database_url` 属性怎么拼出连接串（或走 `DATABASE_URL_OVERRIDE`）；
`upload_path` 怎么把相对路径变成 backend 下的绝对路径；
`ai_enabled` / `wechat_enabled` 两个开关属性；末行 `settings = Settings()` 是模块级单例。

### 第 3 步 · `app/database.py`（29 行）
**连接怎么建。**
重点：`create_engine(pool_pre_ping=True)` 防连接失效；`SessionLocal` 是会话工厂；
`get_db()` 是 FastAPI 依赖，请求结束自动 close；`Base`（`DeclarativeBase`）是模型基类。

### 第 4 步 · `app/models.py`（162 行）
**七张表 + 它们的关系。**
- `Tenant`（知识库）1—N `User`（成员）、1—N `Document`
- `Document` 1—N `Chunk`（分块，级联删除）
- `Chunk.tenant_id` + `Document.tenant_id` —— **租户隔离**的落点
- `User` 1—N `Follow`（关注，保留自早期社交功能）
- `WxLoginState`（扫码会话）、`ChatMessage`（对话历史，带 tenant/user 归属）
- `BigIntPK = BigInteger().with_variant(Integer, "sqlite")` —— 让 SQLite 也能自增（便于离线测试）
- 最后两行 `Index(...)` —— 按「租户+时间」「租户+文档」查询的联合索引

### 第 5 步 · `app/schemas.py`（155 行）
**接口的「形状」。**
- `*Out` 响应模型带 `from_attributes=True`（能从 ORM 对象直接 `model_validate`），如 `UserOut` / `DocumentOut` / `TenantOut`。
- `*Create / *Update / *In` 是输入模型，用 `Field(...)` 做校验。
- `DocumentOut.chunk_count / char_count` 是数据库字段；`UserProfile` 的 followers/documents 等是**统计值**。
- 末尾 `WechatPollOut.model_rebuild()` —— 因 `WechatPollOut` 定义在 `UserOut` 之前、用了字符串前向引用，必须重建解析。

### 第 6 步 · `app/security.py`（33 行）
**密码和令牌。**
`hash_password` / `verify_password` 用 bcrypt；`create_access_token` 把 user id 塞进 `sub` 并设过期；`decode_token` 失败返回 None（不抛异常）。

### 第 7 步 · `app/deps.py`（40 行）
**「当前用户是谁」的唯一出口。**
- `get_current_user`：无 token / token 无效 → 401
- `get_current_user_optional`：未登录返回 None（列表页游客也能浏览）

> 这两个函数在路由里用 `Depends(...)` 注入，是理解接口鉴权的关键。

### 第 8 步 · `app/doc_service.py`（226 行）
**文档 → 文本 → 分块。**
- `extract_text`：按类型分派到 `_extract_pdf` / `_extract_docx` / `_extract_plain`
- `_extract_pdf`：**优先 PyMuPDF 的 `sort=True` 排版顺序模式**（把表单里与标签分离的值贴回标签后），失败回退 pypdf
- `_extract_docx`：按 body 真实顺序遍历「段落 + 表格」交错结构，并去合并单元格的重复
- `normalize` → `split_units`（语义单元，PDF 才合并视觉折行）→ `chunk_text`（聚合到 chunk_size、按整句重叠）
- `_overlap_tail`：重叠长度**硬性封顶**，防止无句末标点的文本滚雪球
- `build_chunks` / `process_document`：写 Chunk 表并更新文档状态

### 第 9 步 · `app/ai_service.py`（334 行，核心）
**手写轻量 RAG。**
1. `_pack / _unpack`：向量 ↔ float32 字节（存 MySQL BLOB）
2. `_cos`：手写余弦相似度
3. `_tokens / _bm25`：中文友好的极简分词（字符二元组）+ BM25 关键词打分
4. `embed_texts`：调百炼 `text-embedding-v3`（每 10 条一批）
5. `refresh_embeddings`：为「尚无向量」的分块补齐向量，带 `_INDEX_LOCK` 串行化 + 租户过滤
6. `search_chunks`：**混合检索**——向量（0.55）+ BM25（0.45）归一后加权融合，Top-K
7. `_system_prompt`：把命中片段（含出处、相似度）拼进 system prompt
8. `chat`：拼历史 + 提问 → 调 `qwen-plus` → 落库 → 返回 `{answer, sources}`
9. `index_document_bg`：上传后开后台线程补索引

### 第 10 步 · `app/wechat_service.py`（233 行）
**微信扫码登录。**
- `create_login_state / get_login_state / confirm_login_state / consume_login_state`：扫码会话状态机（pending → confirmed → consumed）
- `build_authorize_url`（真实）/ `build_mock_scan_url`（Mock）：二维码内容
- `make_qr_data_url`：用 qrcode 生成二维码 data URL
- `login_or_create_user`（真实微信用户）/ `create_mock_user`（Mock 用户）：落库并**自动开个人知识库**
- 头像生成：按首字符画彩色圆形头像，带 CJK 字体候选链（避免中文渲染成「豆腐块」）

### 第 11 步 · `app/routers/`（重点，五个文件）
- **`auth.py`（284 行）**：注册（`_resolve_tenant` 决定建库/加入）/ 登录(JSON) / 登录(表单，给 Swagger) / 我 / 头像 / 微信扫码全链路（qrcode / poll / mock / mock confirm / callback / virtual）
- **`tenants.py`（122 行）**：`/current` / 创建 / 加入 / 成员 / 成员明细
- **`users.py`（99 行）**：⚠️ 静态路径 `/me` 写在 `/{user_id}` **之前**，否则「me」会被当成 id；改资料 / 资料页 / 关注
- **`documents.py`（208 行，核心）**：按顺序读——
  1. `upload_document`：分块读文件 + 大小限制 + 存盘 + 同步解析分块 + 后台补向量
  2. `list_documents`：搜索 / 状态筛选 / 按作者 / 分页（严格按 `tenant_id` 过滤）
  3. `get_document` / `get_document_chunks`：详情 / 分块
  4. `update_document` / `delete_document`：改标题 / 删除（上传者或 owner/admin 才可删）
  5. `reindex_document`：重新解析 + 重建该文档向量
- **`ai.py`（85 行）**：`/status`（是否启用 + 已索引数）/ `/chat` / `/history` / `/reindex`

---

## 三、想动手验证？

```powershell
cd D:\surreal_kb\backend
# 离线冒烟（不需要 MySQL，用 SQLite 临时库）
.\.venv\Scripts\python.exe smoke_test.py
# 知识库全链路（真实 MySQL + 真实百炼 API）
.\.venv\Scripts\python.exe kb_smoke.py
```

边读 `routers/` 边对照这些测试文件，每个接口的预期行为一目了然。

---

## 四、一个请求的完整链路（例子：向知识库提问）

```
前端 POST /api/ai/chat  { question }  (Authorization: Bearer <token> + X-Session-Key: <前端生成>)
  → main.py 交给 ai.router
  → Depends(get_current_user) 强制登录；Depends(get_session_key) 校验请求头
  → ai_service.chat()
      → _system_prompt() → search_chunks()   # 向量 0.55 + BM25 0.45，租户内 Top-K
      → 调百炼 /chat/completions（qwen-plus）
      → 落库 ChatMessage(user + assistant，按 user_id + session_key 隔离)
  → 返回 { answer, sources:[{document_id,title,score,snippet}], session_key }
```

---

## 五、可读性标记说明

- 依赖注入一律用 `Depends(...)`，参数名即语义（`db` = 会话，`user` = 当前用户）
- 「只有上传者/管理员能做」的操作返回 403，未登录返回 401
- 表名复数小写（tenants/users/documents/chunks/follows/...），字段蛇形命名
- 「租户隔离」是所有查询的第一道条件：文档、分块、检索都带 `tenant_id`

---

## 六、历史沿革（阅读时可能遇到的旧词）

本项目由早期的「视频站（SurrealVideo）」改造而来，仍能看到旧痕：

- `README` / 旧注释里偶有「视频」「Video」字样；`index.html` 的 `<title>` 尚未更新。
- `routers/auth.py` 里 Mock 授权页文案仍是旧站名。
- 库名 `surrealkb`、部分脚本名沿用旧路径（已改新路径）。
- 旧的 `videos / likes / favorites / video_embeddings` 表已从 `models.py` 移除，代码不再引用。

**一句话看懂新版**：文档丢进来 → 提取文本、切成语义分块 → 每块算 1024 维向量存 BLOB →
提问时向量 + 关键词混合检索出最相关几块 → 拼进 prompt 交给大模型 → 答案带出处返回。
不引入向量库，几千块以内全内存算相似度就够。
