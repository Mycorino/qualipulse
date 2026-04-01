from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DATABASE_URL: str = "sqlite:///./auto_interview.db"
    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""
    SECRET_KEY: str = "change-me-to-a-random-string"
    UPLOAD_DIR: str = "./uploads"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours

    # Cloudflare R2 (optional — local disk used when not set)
    R2_ACCOUNT_ID: str = ""
    R2_ACCESS_KEY_ID: str = ""
    R2_SECRET_ACCESS_KEY: str = ""
    R2_BUCKET: str = ""
    R2_PUBLIC_URL: str = ""  # e.g. https://pub-xxx.r2.dev or https://audio.yourapp.com


settings = Settings()
