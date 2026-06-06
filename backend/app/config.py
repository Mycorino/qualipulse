import sys
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
    # Legacy tier price IDs (kept so existing subscriptions still resolve).
    STRIPE_PRICE_STARTER: str = ""
    STRIPE_PRICE_PRO: str = ""
    # Credits-based plan price IDs. Configure these in Stripe and set them
    # in .env / Secret Manager. Leave blank in dev — the checkout endpoint
    # returns 503 if a requested plan has no price configured, so legacy
    # flows keep working without these vars.
    STRIPE_PRICE_EXPLORATION_MONTHLY: str = ""
    STRIPE_PRICE_EXPLORATION_ANNUAL: str = ""
    STRIPE_PRICE_TEAM_MONTHLY: str = ""
    STRIPE_PRICE_TEAM_ANNUAL: str = ""
    STRIPE_PRICE_AGENCY_MONTHLY: str = ""
    STRIPE_PRICE_AGENCY_ANNUAL: str = ""
    # One-time prepaid credit pack price IDs (PR 3).
    STRIPE_PRICE_PACK_25: str = ""
    STRIPE_PRICE_PACK_50: str = ""
    STRIPE_PRICE_PACK_100: str = ""

    # Google OAuth (Sign in with Google). Leave blank to disable —
    # /auth/google/login returns 503 when unconfigured. The redirect URI
    # registered in Google Cloud Console must match
    # ``{API_BASE_URL}/auth/google/callback``.
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_REDIRECT_URI: str = ""

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


def _recover_empty_dev_keys_from_env_file() -> None:
    """Dev safety net: recover AI keys that an empty *exported* env var shadowed.

    pydantic-settings ranks real environment variables above the ``.env``
    file, so a shell that exports ``ANTHROPIC_API_KEY=`` (empty) — as some
    launch environments do — silently wins over a perfectly good key in
    ``.env``. The copilot then drops into its offline stub with no obvious
    cause. Outside production we re-read the ``.env`` file directly and fill
    in any AI key that resolved empty.

    Scoped to non-production and to AI keys only: production injects secrets
    via the real environment (Secret Manager) and never ships a ``.env``, so
    this is a no-op there.
    """
    # Tests deliberately run with empty AI keys to exercise the offline
    # stub path; never let the .env override that.
    if settings.is_production or "pytest" in sys.modules or not _ENV_FILE.exists():
        return
    file_values: dict[str, str] = {}
    try:
        for raw in _ENV_FILE.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            file_values[key.strip()] = value.strip().strip("\"'")
    except OSError:
        return
    for field in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        if not getattr(settings, field, "") and file_values.get(field):
            setattr(settings, field, file_values[field])


_recover_empty_dev_keys_from_env_file()


# Hard fail in production if SECRET_KEY is still the default placeholder —
# a predictable signing key means any attacker can mint admin tokens. The
# development default is intentionally ugly so this check catches it.
if settings.is_production and settings.SECRET_KEY == "change-me-to-a-random-string":
    raise RuntimeError(
        "SECRET_KEY is set to its development default in production. "
        "Set a strong random value via Secret Manager before starting the service."
    )
