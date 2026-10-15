"""应用配置：从环境变量 / .env 读取。"""
import warnings
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/

# 明显不安全的密钥值（默认值/占位符）
_WEAK_KEYS = {"", "change-me", "changeme", "change_me", "secret", "secret-key",
              "your-secret-key", "xxx", "test"}
_MIN_SECRET_LEN = 16


class Settings(BaseSettings):
    # pydantic-settings 的规则是：环境变量 / .env 里的值优先级高于这里写的默认值，且大小写不敏感
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "SurrealKB"
    # 调试模式：true 时日志更详细（勿在生产开启）
    debug: bool = False
    # 必须显式设置（backend/.env 的 SECRET_KEY）。留空/过弱将拒绝启动，避免 JWT 被伪造。
    secret_key: str = ""
    # 仅本地临时调试可设 true 放行弱密钥（会打印醒目警告）。生产务必保持 false。
    allow_insecure_secret: bool = False
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7

    db_host: str = "127.0.0.1"
    db_port: int = 3306
    db_user: str = "root"
    db_password: str = ""
    db_name: str = "surrealkb"
    # 可选：直接指定完整连接串（留空则用上面的 MySQL 参数拼接）
    database_url_override: str = ""

    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    upload_dir: str = "uploads"
    max_avatar_mb: int = 5

    # ---------- 知识库文档 ----------
    max_doc_mb: int = 50                      # 单个文档最大体积（MB）
    chunk_size: int = 800                     # 分块目标字符数
    chunk_overlap: int = 120                  # 相邻分块重叠字符数
    allow_new_tenant: bool = True             # 是否允许注册时自动创建新知识库

    # ---------- 反滥用 / 每日配额（防刷 AI 额度与磁盘）----------
    # 每个用户每天最多问 AI 的次数（0 = 不限制）。直接决定你的百炼账单上限，务必设置。
    ai_daily_quota_per_user: int = 200
    # 全站每天最多 AI 提问次数（0 = 不限制）。作为总闸，防止被批量小号绕过单用户配额。
    ai_daily_quota_global: int = 3000
    # 每个用户每天最多上传文档次数（0 = 不限制）。
    upload_daily_quota_per_user: int = 30
    # 每个知识库最多容纳的文档数（0 = 不限制），防止塞满磁盘。
    max_docs_per_tenant: int = 500
    # 是否关闭注册（true = 只能由已有用户用邀请码加入，杜绝批量小号）。
    disable_register: bool = False

    # ---------- 登录防爆破（账号级）----------
    # ratelimit.py 只按「IP + 路径」限流，攻击者换 IP 就能继续对同一账号定向爆破，
    # 这里再按「用户名」补一层失败锁定。连续失败达到阈值后锁定一段时间，登录成功即清零。
    # 0 = 关闭该保护。
    login_max_failures: int = 5
    login_lockout_seconds: int = 900

    # ---------- 微信扫码登录（微信开放平台「网站应用」）----------
    # 留空则自动进入本地 Mock 模式（无需真实公众号即可演示）
    wechat_app_id: str = ""
    wechat_app_secret: str = ""
    wechat_redirect_uri: str = "http://localhost:8000/api/auth/wx/callback"
    public_base_url: str = "http://localhost:8000"
    wx_state_ttl_seconds: int = 600
    # 是否允许「无真实 AppID 时的模拟扫码登录」（本地开发用）。生产环境应关闭。
    enable_wechat_mock: bool = True
    # 是否开放 /api/auth/wx/virtual（一键虚拟登录，无任何鉴权）。**仅本地开发**，生产必须关闭。
    enable_virtual_login: bool = False

    # ---------- 微信扫码登录（个人主体方案：小程序码中转）----------
    # 个人主体无法申请开放平台「网站应用」，改用小程序解出带参小程序码做登录跳板。
    # 留空则回到 Mock 模式。三项模式优先级：real(网站应用) > mp(小程序) > mock。
    wx_mp_app_id: str = ""
    wx_mp_app_secret: str = ""
    # 小程序码指向的页面路径（必须是已存在且已发布的页面，不能以 / 开头、不能带参数）
    wx_mp_page: str = "pages/login/index"
    # 小程序码版本：release 正式版 / trial 体验版 / develop 开发版
    # 开发期页面还没发布时，用 trial 配合下方的 check_path=false 可以先生成码
    wx_mp_env_version: str = "release"
    # 是否校验 page 路径存在。页面尚未发布时必须设为 false，否则接口返回 41030
    wx_mp_check_path: bool = True
    # scene 场景值最大 32 字符，登录票据固定用 16 字节 hex（正好 32 字符）
    wx_mp_ticket_bytes: int = 16

    # ---------- AI（阿里云百炼 / DashScope，OpenAI 兼容模式）----------
    dashscope_api_key: str = ""
    dashscope_base: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    ai_chat_model: str = "qwen-plus"
    ai_embed_model: str = "text-embedding-v3"
    ai_embed_dim: int = 1024
    ai_top_k: int = 4

    @model_validator(mode="after")
    def _guard_secret_key(self) -> "Settings":
        key = (self.secret_key or "").strip()
        weak = key.lower() in _WEAK_KEYS or len(key) < _MIN_SECRET_LEN
        if weak and not self.allow_insecure_secret:
            raise ValueError(
                "SECRET_KEY 未设置或过弱：请在 backend/.env 设置一个随机长字符串，例如："
                '  python -c "import secrets;print(secrets.token_hex(32))"\n'
                "（仅本地临时调试可设 ALLOW_INSECURE_SECRET=true 绕过，生产禁用）"
            )
        if weak and self.allow_insecure_secret:
            warnings.warn(
                "[安全警告] SECRET_KEY 过弱，ALLOW_INSECURE_SECRET=true 仅供本地开发，切勿用于生产！",
                stacklevel=2,
            )
        return self

    @property
    def ai_enabled(self) -> bool:
        return bool(self.dashscope_api_key)

    @property
    def quota_enabled(self) -> bool:
        return bool(self.ai_daily_quota_per_user or self.ai_daily_quota_global)

    @property
    def wechat_enabled(self) -> bool:
        return bool(self.wechat_app_id and self.wechat_app_secret)

    @property
    def wechat_mp_enabled(self) -> bool:
        """小程序扫码登录是否可用（需 AppID + AppSecret）。"""
        return bool(self.wx_mp_app_id and self.wx_mp_app_secret)

    @property
    def wechat_mode(self) -> str:
        """当前微信登录模式：real（网站应用）/ mp（小程序）/ mock（本地模拟）。"""
        if self.wechat_enabled:
            return "real"
        if self.wechat_mp_enabled:
            return "mp"
        return "mock"

    @property
    def database_url(self) -> str:
        if self.database_url_override:
            return self.database_url_override
        return (
            f"mysql+pymysql://{self.db_user}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}?charset=utf8mb4"
        )

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def upload_path(self) -> Path:
        p = Path(self.upload_dir)
        if not p.is_absolute():
            p = BASE_DIR / p
        return p


settings = Settings()
