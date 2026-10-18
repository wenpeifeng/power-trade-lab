"""应用配置。

通过环境变量或 .env 文件加载，本地起步全部有合理默认值，零配置即可运行。
"""
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# 项目根目录：backend/app/config.py -> 上两级是 backend/，再上一级是项目根
PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BACKEND_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- 应用 ----
    APP_NAME: str = "Power Trade Lab · 电力交易演练台"
    APP_VERSION: str = "0.1.0"
    DEBUG: bool = True
    ENVIRONMENT: str = "development"
    # 生产环境须填写实际访问域名/IP；开发环境不启用 Host 拦截。
    ALLOWED_HOSTS: list[str] = []

    # ---- 认证 ----
    # 生产环境必须通过环境变量提供；开发环境缺省时会在 data/credentials
    # 自动生成仅本机可读的随机密钥，绝不使用仓库内固定默认值。
    JWT_SECRET_KEY: str = ""
    JWT_SECRET_FILE: Path = PROJECT_ROOT / "data" / "credentials" / "jwt-secret.key"
    JWT_ACCESS_TOKEN_HOURS: int = 24
    AUTH_COOKIE_NAME: str = "power_session"
    LOGIN_MAX_FAILURES: int = 5
    LOGIN_FAILURE_WINDOW_MINUTES: int = 15
    REGISTER_MAX_ATTEMPTS: int = 5
    REGISTER_WINDOW_MINUTES: int = 60

    # ---- 数据库 ----
    # SQLite 起步，零配置；扩展时改 DATABASE_URL=postgresql://... 即可
    DATABASE_URL: str = f"sqlite:///{BACKEND_ROOT / 'power_trade.db'}"

    # ---- CORS（前端开发地址）----
    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5173",
    ]

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.strip().lower() in {"production", "prod"}

    def validate_production_security(self) -> None:
        if not self.is_production:
            return
        if not self.ALLOWED_HOSTS or "*" in self.ALLOWED_HOSTS:
            raise RuntimeError("生产环境必须配置非通配符 ALLOWED_HOSTS")
        if not self.CORS_ORIGINS or "*" in self.CORS_ORIGINS:
            raise RuntimeError("生产环境必须配置非通配符 CORS_ORIGINS")

    # ---- 文件存储 ----
    DATA_DIR: Path = PROJECT_ROOT / "data"
    QUESTION_DIR: Path = PROJECT_ROOT / "data" / "questions"
    POLICY_DIR: Path = PROJECT_ROOT / "data" / "policies"
    ATTACHMENT_DIR: Path = PROJECT_ROOT / "data" / "attachments"
    HISTORY_DIR: Path = PROJECT_ROOT / "data" / "history"
    RAW_PUBLIC_DIR: Path = PROJECT_ROOT / "data" / "raw" / "public"
    CREDENTIAL_DIR: Path = PROJECT_ROOT / "data" / "credentials"
    LEARNING_BOOK_DIR: Path = PROJECT_ROOT / "data" / "learning_books"

    # ---- 外部接入安全边界 ----
    ASSET_UPLOAD_MAX_MB: int = 100
    OUTBOUND_FETCH_MAX_MB: int = 50
    # 默认禁止访问本机/内网；确需接入时仅填写精确主机名，逗号分隔。
    OUTBOUND_PRIVATE_HOST_ALLOWLIST: str = ""

    # ---- MinerU 教材解析服务 ----
    # 推荐使用项目外的共享服务，业务系统仅通过 HTTP 调用，不加载模型依赖。
    # 留空时 PDF 使用全文降级解析；DOCX 等格式需要 MinerU。
    MINERU_ENABLED: bool = False
    MINERU_API_URL: str = ""
    MINERU_BACKEND: str = "hybrid-engine"
    MINERU_EFFORT: str = "medium"
    MINERU_TIMEOUT_SEC: int = 1800

    # ---- LLM（按登录用户 BYOK，不接受全局开发者 API Key）----
    # 用户凭证的独立加密主密钥。生产环境必须显式配置 Fernet Key；
    # 开发环境留空时生成到被忽略的本机 credentials 目录。
    LLM_CONFIG_MASTER_KEY: str = ""
    LLM_CONFIG_MASTER_KEY_FILE: Path = (
        PROJECT_ROOT / "data" / "credentials" / "llm-master.key"
    )

    # ---- 知识库检索 ----
    KB_EMBEDDING_MODEL: str = "BAAI/bge-small-zh-v1.5"
    KB_EMBEDDING_DIM: int = 512
    KB_RERANKER_MODEL: str = ""

    # ---- 爬虫 ----
    # 总开关：false 时调度器不注册任何定时任务，手动触发也会立即返回跳过。
    CRAWLER_ENABLED: bool = True
    CRAWLER_RATE_LIMIT_SEC: float = 1.0  # 请求间隔（≤1 req/s，规避反爬）
    CRAWLER_USER_AGENT: str = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )

    # ---- 和风天气（国内气象辅助数据）----
    # 开源版本显式默认关闭。部署者必须主动开启，并配置自己的开发者凭证。
    QWEATHER_ENABLED: bool = False
    # API Host 是控制台分配的专属域名，不要填写旧的公共 api.qweather.com。
    QWEATHER_API_HOST: str = ""
    # api_key | jwt
    QWEATHER_AUTH_TYPE: str = "api_key"
    QWEATHER_API_KEY: str = ""
    # JWT 模式需要项目ID、凭据ID和本地 Ed25519 私钥文件。
    QWEATHER_PROJECT_ID: str = ""
    QWEATHER_CREDENTIAL_ID: str = ""
    QWEATHER_PRIVATE_KEY_PATH: Path = PROJECT_ROOT / "data" / "credentials" / "qweather-ed25519-private.pem"
    QWEATHER_FORECAST_HOURS: str = "24h"
    # JSON 对象：{"省份":{"city":"城市","location_id":"和风LocationID"}}
    QWEATHER_LOCATIONS_JSON: str = ""

    @property
    def qweather_configured(self) -> bool:
        """只判断配置是否齐全，不读取或暴露凭证内容。"""
        if not self.QWEATHER_ENABLED:
            return False
        if not self.QWEATHER_API_HOST.strip():
            return False
        auth_type = self.QWEATHER_AUTH_TYPE.strip().lower()
        if auth_type == "api_key":
            return bool(self.QWEATHER_API_KEY.strip())
        if auth_type == "jwt":
            return (
                bool(self.QWEATHER_PROJECT_ID.strip())
                and bool(self.QWEATHER_CREDENTIAL_ID.strip())
                and self.QWEATHER_PRIVATE_KEY_PATH.is_file()
            )
        return False


settings = Settings()


def ensure_dirs() -> None:
    """启动时确保数据目录存在。"""
    for d in (
        settings.DATA_DIR,
        settings.QUESTION_DIR,
        settings.POLICY_DIR,
        settings.ATTACHMENT_DIR,
        settings.HISTORY_DIR,
        settings.RAW_PUBLIC_DIR,
        settings.CREDENTIAL_DIR,
        settings.LEARNING_BOOK_DIR,
    ):
        d.mkdir(parents=True, exist_ok=True)
