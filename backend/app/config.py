from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Core
    DATABASE_URL: str = "sqlite:///./auto_interview.db"
    SECRET_KEY: str = "change-me-to-a-random-string"
    ENVIRONMENT: str = "development"  # "development" | "staging" | "production"
    APP_BASE_URL: str = "http://localhost:5173"
    DEBUG: bool = True

    # Auth
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # AI
    ANTHROPIC_API_KEY: str = ""
    OPENAI_API_KEY: str = ""

    # Storage
    UPLOAD_DIR: str = "./uploads"
    MAX_AUDIO_SIZE_MB: int = 50
    MAX_TEXT_LENGTH: int = 10000

    # CORS — comma-separated origins, e.g. "https://app.yoursite.com,https://yoursite.com"
    ALLOWED_ORIGINS: str = "*"

    # Email (SendGrid)
    SENDGRID_API_KEY: str = ""
    EMAIL_FROM: str = "noreply@qualipulse.com"
    EMAIL_FROM_NAME: str = "QualiPulse"

    # Stripe (billing)
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""
    STRIPE_PRICE_STARTER: str = ""
    STRIPE_PRICE_PRO: str = ""

    # Sentry
    SENTRY_DSN: str = ""

    # Cloudflare R2 (optional — local disk used when not set)
    R2_ACCOUNT_ID: str = ""
    R2_ACCESS_KEY_ID: str = ""
    R2_SECRET_ACCESS_KEY: str = ""
    R2_BUCKET: str = ""
    R2_PUBLIC_URL: str = ""
    R2_JURISDICTION: str = ""  # "" (default) or "eu" / "fedramp" for region-locked buckets

    # Admin
    ADMIN_SECRET_KEY: str = ""  # If empty, admin routes return 403

    # Sales Slack webhook — posts a message every time a new account
    # completes onboarding. Optional: if empty, notifications are skipped.
    SALES_SLACK_WEBHOOK_URL: str = ""

    # Rate limits (requests per minute)
    RATE_LIMIT_PUBLIC: str = "60/minute"     # Interview public endpoints
    RATE_LIMIT_AUTH: str = "10/minute"       # Login/signup
    RATE_LIMIT_DEFAULT: str = "120/minute"   # Authenticated API calls

    @property
    def allowed_origins_list(self) -> list[str]:
        if self.ALLOWED_ORIGINS == "*":
            return ["*"]
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"


settings = Settings()


# Hard fail in production if SECRET_KEY is still the default placeholder —
# a predictable signing key means any attacker can mint admin tokens. The
# development default is intentionally ugly so this check catches it.
if settings.is_production and settings.SECRET_KEY == "change-me-to-a-random-string":
    raise RuntimeError(
        "SECRET_KEY is set to its development default in production. "
        "Set a strong random value via Secret Manager before starting the service."
    )
