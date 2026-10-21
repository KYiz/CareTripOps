import os
from dataclasses import dataclass


DEMO_NONCE_DEFAULT = "caretrip-local-demo-only"
AUTH_SECRET_DEFAULT = "caretrip-local-auth-only"


@dataclass(frozen=True)
class Settings:
    app_env: str = os.getenv("APP_ENV", "development").lower()
    database_url: str = os.getenv(
        "DATABASE_URL", "postgresql+psycopg://caretrip:caretrip@localhost:5432/caretrip"
    )
    model_mode: str = os.getenv("MODEL_MODE", "mock_llm")
    model_name: str = os.getenv("MODEL_NAME", "gpt-4o-mini")
    llm_provider: str = os.getenv("LLM_PROVIDER", "gemini").lower()
    gemini_requirements_model: str = os.getenv("GEMINI_REQUIREMENTS_MODEL", "gemini-3.8-flash")
    max_llm_calls: int = int(os.getenv("MAX_LLM_CALLS_PER_CASE", "7"))
    max_reranks: int = int(os.getenv("MAX_RERANKS", "1"))
    max_clarifications: int = int(os.getenv("MAX_CLARIFICATIONS", "2"))
    frontend_origin: str = os.getenv("FRONTEND_ORIGIN", "http://localhost:8080")
    demo_nonce_secret: str = os.getenv("DEMO_NONCE_SECRET", DEMO_NONCE_DEFAULT)
    gemini_live_model: str = os.getenv("GEMINI_LIVE_MODEL", "gemini-3.8-live")
    max_live_sessions_per_case: int = int(os.getenv("MAX_LIVE_SESSIONS_PER_CASE", "2"))
    # Case creation bounds total model spend: each Case allows at most MAX_LLM_CALLS_PER_CASE calls.
    case_create_limit_per_ip: int = int(os.getenv("CASE_CREATE_LIMIT_PER_IP_PER_HOUR", "30"))
    case_create_limit_global: int = int(os.getenv("CASE_CREATE_LIMIT_GLOBAL_PER_HOUR", "300"))
    # Only trust X-Real-IP when the API is reachable solely through the bundled Nginx proxy.
    trust_proxy: bool = os.getenv("TRUST_PROXY", "false").lower() == "true"
    # Rate limits are shared between API processes through Redis when set; required in production.
    redis_url: str = os.getenv("REDIS_URL", "")
    # Bearer token Prometheus must send to read /metrics; without it /metrics is only served on the internal network.
    metrics_token: str = os.getenv("METRICS_TOKEN", "")
    # Pepper for login-code and session hashes.
    auth_secret: str = os.getenv("AUTH_SECRET", AUTH_SECRET_DEFAULT)
    session_days: int = int(os.getenv("SESSION_DAYS", "30"))
    login_code_minutes: int = int(os.getenv("LOGIN_CODE_MINUTES", "10"))
    # Approving a payment, cancelling a booking or deleting the account needs a code confirmed this recently.
    step_up_minutes: int = int(os.getenv("STEP_UP_MINUTES", "10"))
    login_code_limit_per_email: int = int(os.getenv("LOGIN_CODE_LIMIT_PER_EMAIL_PER_HOUR", "5"))
    login_code_limit_per_ip: int = int(os.getenv("LOGIN_CODE_LIMIT_PER_IP_PER_HOUR", "30"))
    # Development convenience: return the login code in the API response so the demo needs no mailbox.
    auth_dev_return_code: bool = os.getenv("AUTH_DEV_RETURN_CODE", "true").lower() == "true"
    # Compose runs workflows in a separate worker service; a bare `uvicorn` runs one in-process.
    embedded_worker: bool = os.getenv("EMBEDDED_WORKER", "true").lower() == "true"
    worker_concurrency: int = int(os.getenv("WORKER_CONCURRENCY", "4"))
    worker_poll_seconds: float = float(os.getenv("WORKER_POLL_SECONDS", "0.5"))
    log_format: str = os.getenv("LOG_FORMAT", "json").lower()
    log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()
    sentry_dsn: str = os.getenv("SENTRY_DSN", "")
    # Supplier: without a base URL the simulator runs in-process (development and tests only).
    supplier_base_url: str = os.getenv("SUPPLIER_BASE_URL", "")
    supplier_api_key: str = os.getenv("SUPPLIER_API_KEY", "sim-local-key")
    # Payments: "simulated" authorizes instantly and is labelled as such; "stripe" uses Stripe Checkout.
    payment_provider: str = os.getenv("PAYMENT_PROVIDER", "simulated").lower()
    stripe_secret_key: str = os.getenv("STRIPE_SECRET_KEY", "")
    stripe_webhook_secret: str = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    stripe_api_base: str = os.getenv("STRIPE_API_BASE", "")  # Only for stripe-mock in tests.
    # Staff who work the evidence review queue.
    advisor_emails: tuple[str, ...] = tuple(e.strip().lower() for e in os.getenv("ADVISOR_EMAILS", "").split(",") if e.strip())
    # Shown on trip cards and the help screen when set, e.g. "0800 123 456".
    support_phone: str = os.getenv("SUPPORT_PHONE", "")
    # Sign-in by text message: "off", "console" (development) or "twilio".
    sms_backend: str = os.getenv("SMS_BACKEND", "console").lower()
    twilio_account_sid: str = os.getenv("TWILIO_ACCOUNT_SID", "")
    twilio_auth_token: str = os.getenv("TWILIO_AUTH_TOKEN", "")
    twilio_from: str = os.getenv("TWILIO_FROM", "")
    email_backend: str = os.getenv("EMAIL_BACKEND", "console").lower()
    email_from: str = os.getenv("EMAIL_FROM", "CareTrip <no-reply@caretrip.local>")
    smtp_host: str = os.getenv("SMTP_HOST", "")
    smtp_port: int = int(os.getenv("SMTP_PORT", "587"))
    smtp_user: str = os.getenv("SMTP_USER", "")
    smtp_password: str = os.getenv("SMTP_PASSWORD", "")

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"


def validate_settings(config: Settings) -> None:
    """Refuse to start with configuration that is only safe for a local demo."""
    if config.app_env not in {"development", "production"}:
        raise RuntimeError("APP_ENV must be development or production")
    if config.model_mode not in {"mock_llm", "api"}:
        raise RuntimeError("MODEL_MODE must be mock_llm or api")
    if config.llm_provider not in {"openai", "gemini"}:
        raise RuntimeError("LLM_PROVIDER must be openai or gemini")
    if config.case_create_limit_per_ip < 1 or config.case_create_limit_global < 1:
        raise RuntimeError("Case creation limits must be positive")
    if config.email_backend not in {"console", "smtp"}:
        raise RuntimeError("EMAIL_BACKEND must be console or smtp")
    if config.sms_backend not in {"off", "console", "twilio"}:
        raise RuntimeError("SMS_BACKEND must be off, console or twilio")
    if config.sms_backend == "twilio" and not (config.twilio_account_sid and config.twilio_auth_token and config.twilio_from):
        raise RuntimeError("SMS_BACKEND=twilio requires TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN and TWILIO_FROM")
    if config.payment_provider not in {"simulated", "stripe"}:
        raise RuntimeError("PAYMENT_PROVIDER must be simulated or stripe")
    if config.payment_provider == "stripe" and not config.stripe_secret_key.startswith(("sk_test_", "sk_live_")):
        raise RuntimeError("PAYMENT_PROVIDER=stripe requires STRIPE_SECRET_KEY (sk_test_... or sk_live_...)")
    if config.email_backend == "smtp" and not config.smtp_host:
        raise RuntimeError("EMAIL_BACKEND=smtp requires SMTP_HOST")
    if config.is_production:
        if config.demo_nonce_secret == DEMO_NONCE_DEFAULT or len(config.demo_nonce_secret) < 32:
            raise RuntimeError("Production requires DEMO_NONCE_SECRET of at least 32 characters")
        if config.auth_secret == AUTH_SECRET_DEFAULT or len(config.auth_secret) < 32:
            raise RuntimeError("Production requires AUTH_SECRET of at least 32 characters")
        if not config.frontend_origin.startswith("https://"):
            raise RuntimeError("Production requires an https FRONTEND_ORIGIN")
        if config.email_backend != "smtp":
            raise RuntimeError("Production requires EMAIL_BACKEND=smtp so login codes reach travelers")
        if config.sms_backend == "console":
            raise RuntimeError("Production requires SMS_BACKEND=twilio or off; console only prints messages")
        if config.auth_dev_return_code:
            raise RuntimeError("Production requires AUTH_DEV_RETURN_CODE=false")
        if config.payment_provider != "stripe" or not config.stripe_webhook_secret:
            raise RuntimeError("Production requires PAYMENT_PROVIDER=stripe and STRIPE_WEBHOOK_SECRET")
        if not config.redis_url:
            raise RuntimeError("Production requires REDIS_URL so rate limits hold across API processes")
        if not config.supplier_base_url:
            raise RuntimeError("Production requires SUPPLIER_BASE_URL; the in-process simulator is for development")


settings = Settings()
