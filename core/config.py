"""
core/config.py — Load env vars + validate khi app khởi động
"""
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    groq_api_key: str
    langfuse_public_key: str
    langfuse_secret_key: str
    langfuse_host: str
    default_model: str
    log_level: str
    app_env: str
    cors_origins: tuple        # tuple vì frozen=True yêu cầu hashable
    max_history_turns: int     # số lượt tối đa giữ trong history
    max_retries: int           # số lần retry tối đa khi gặp lỗi transient
    retry_delay_s: float       # base delay giữa các retry (exponential backoff)

    def validate(self) -> None:
        missing = [
            name for name, val in [
                ("GROQ_API_KEY",          self.groq_api_key),
                ("LANGFUSE_PUBLIC_KEY",   self.langfuse_public_key),
                ("LANGFUSE_SECRET_KEY",   self.langfuse_secret_key),
            ] if not val
        ]
        if missing:
            raise EnvironmentError(
                f"❌ Thiếu env vars: {', '.join(missing)}\n"
                "👉 Copy .env.example → .env rồi điền API keys vào."
            )


def get_settings() -> Settings:
    cors_raw = os.getenv("CORS_ORIGINS", "*")
    cors_origins = tuple(o.strip() for o in cors_raw.split(","))
    s = Settings(
        groq_api_key=os.getenv("GROQ_API_KEY", ""),
        langfuse_public_key=os.getenv("LANGFUSE_PUBLIC_KEY", ""),
        langfuse_secret_key=os.getenv("LANGFUSE_SECRET_KEY", ""),
        langfuse_host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
        default_model=os.getenv("DEFAULT_MODEL", "groq/llama-3.3-70b-versatile"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        app_env=os.getenv("APP_ENV", "development"),
        cors_origins=cors_origins,
        max_history_turns=int(os.getenv("MAX_HISTORY_TURNS", "20")),
        max_retries=int(os.getenv("MAX_RETRIES", "3")),
        retry_delay_s=float(os.getenv("RETRY_DELAY_S", "1.0")),
    )
    s.validate()
    return s


settings = get_settings()
