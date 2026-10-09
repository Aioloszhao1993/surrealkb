"""应用配置：从环境变量 / .env 读取。"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent  # backend/


class Settings(BaseSettings):
    # pydantic-settings 的规则是：环境变量 / .env 里的值优先级高于这里写的默认值，且大小写不敏感
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    app_name: str = "SurrealVideo"
    secret_key: str = "change-me"
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
    max_video_mb: int = 1024
    max_avatar_mb: int = 5

    # ---------- 微信扫码登录（微信开放平台「网站应用」）----------
    # 留空则自动进入本地 Mock 模式（无需真实公众号即可演示）
    wechat_app_id: str = ""
    wechat_app_secret: str = ""
    wechat_redirect_uri: str = "http://localhost:8000/api/auth/wx/callback"
    public_base_url: str = "http://localhost:8000"
    wx_state_ttl_seconds: int = 600

    # ---------- AI（阿里云百炼 / DashScope，OpenAI 兼容模式）----------
    dashscope_api_key: str = ""
    dashscope_base: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    ai_chat_model: str = "qwen-plus"
    ai_embed_model: str = "text-embedding-v3"
    ai_embed_dim: int = 1024
    ai_top_k: int = 3

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
