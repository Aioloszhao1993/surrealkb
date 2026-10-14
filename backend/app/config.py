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
    db_name: str = "video_fastqpi"
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
    def wechat_enabled(self) -> bool:
        return bool(self.wechat_app_id and self.wechat_app_secret)

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
