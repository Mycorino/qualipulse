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

    # TTS voice for the AI interviewer. gpt-4o-mini-tts follows per-language
    # accent/tone instructions, so non-English interviews get a native-sounding
    # voice instead of tts-1's anglophone prosody. Env-overridable to pin back
    # to "tts-1"/"alloy" if the newer model misbehaves.
    TTS_MODEL: str = "gpt-4o-mini-tts"
    TTS_VOICE: str = "coral"

    # Claude model IDs — single source of truth (see services/ai_models.py).
    # Blank => use the pinned default in ai_models.py. Set these to swap a model
    # in production without a code deploy (e.g. when Anthropic retires one).
    MODEL_SONNET: str = ""
    MODEL_OPUS: str = ""
    MODEL_HAIKU: str = ""
    # Interview-analysis synthesis model. Blank => the Opus pin (see
    # ai_models.analysis()). Set to a Sonnet id to dial the analysis path back
    # to cheaper synthesis without touching the Copilot's Opus usage.
    MODEL_ANALYSIS: str = ""
    # When true, resolve the newest available model per family from the Models
    # API at startup (falls back to the pinned/env value on any error). Off by
    # default: a brand-new model can change the request surface (e.g. dropped
    # temperature/budget_tokens), so opting in is a deliberate choice.
    MODEL_AUTO_LATEST: bool = False

    # Storage
    UPLOAD_DIR: str = "./uploads"
    MAX_AUDIO_SIZE_MB: int = 50
    MAX_TEXT_LENGTH: int = 10000
    # Audio retention: participant audio files (recordings + TTS) are purged
    # for interviews completed more than this many days ago when the
    # /admin/retention/run endpoint is hit. 0 = retention purge disabled.
    # Transcripts are always kept — the retention policy covers audio only.
    RETENTION_AUDIO_DAYS: int = 0

    # CORS — comma-separated origins, e.g. "https://app.yoursite.com,https://yoursite.com"
    ALLOWED_ORIGINS: str = "*"

    # Email (SendGrid)
    SENDGRID_API_KEY: str = ""
    # SendGrid Event Webhook verification key (base64 DER, copied from
    # SendGrid > Settings > Mail Settings > Event Webhook). Unset disables
    # the webhook outside development — see routers/email_events.py.
    SENDGRID_WEBHOOK_PUBLIC_KEY: str = ""
    EMAIL_FROM: str = "noreply@qualipulse.com"
    EMAIL_FROM_NAME: str = "QualiPulse"

    # Stripe (billing)
    STRIPE_SECRET_KEY: str = ""
    # Publishable key — served to the frontend via GET /billing/config to
    # enable in-app Embedded Checkout. Leave blank to fall back to the
    # hosted checkout.stripe.com redirect flow.
    STRIPE_PUBLISHABLE_KEY: str = ""
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
    # Stripe Tax — enable only once tax registration is configured in the
    # Stripe dashboard, otherwise Checkout session creation 400s. When on,
    # Checkout computes VAT automatically and collects business VAT IDs.
    STRIPE_AUTOMATIC_TAX: bool = False
    # Stripe Customer Portal login page (Settings -> Billing -> Customer
    # portal -> login link). A permanent URL where a customer types their
    # email and Stripe mails them a link into their own portal. Used in
    # billing emails, where we can't authenticate the reader. Blank hides
    # the link. Only ever shown to workspaces that have a Stripe customer:
    # for anyone else Stripe silently sends nothing, which reads as a bug.
    STRIPE_PORTAL_LOGIN_URL: str = ""

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
    # haveibeenpwned k-anonymity check on new passwords. Always on in
    # production; set true to also enable in dev/staging. Fail-open on
    # network errors either way.
    PASSWORD_BREACH_CHECK: bool = False

    RATE_LIMIT_PUBLIC: str = "60/minute"     # Interview public endpoints
    RATE_LIMIT_AUTH: str = "10/minute"       # Login/signup
    RATE_LIMIT_DEFAULT: str = "120/minute"   # Authenticated API calls
    RATE_LIMIT_COPILOT: str = "10/minute"    # Copilot turns (each = up to 8 Opus calls)

    # Per-workspace daily spend ceiling for copilot turns (USD, summed from
    # AIUsageLog). 0 disables the gate.
    COPILOT_DAILY_COST_LIMIT_USD: float = 25.0

    # Per-workspace daily spend ceiling for the public participant interview
    # loop (STT + Claude + TTS, summed from AIUsageLog). New interview starts
    # are blocked at the limit; in-flight interviews get a 2x grace ceiling
    # so a real participant mid-session isn't cut off. 0 disables the gate.
    INTERVIEW_DAILY_COST_LIMIT_USD: float = 50.0

    # Recontact invitations: max panel invites one workspace may send per
    # rolling 24h. Protects the sending domain's reputation and the panel
    # itself from over-contacting. 0 disables recontact sending entirely.
    INVITE_DAILY_LIMIT: int = 200

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
