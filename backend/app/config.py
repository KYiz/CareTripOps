import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
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
    demo_nonce_secret: str = os.getenv("DEMO_NONCE_SECRET", "caretrip-local-demo-only")
    gemini_live_model: str = os.getenv("GEMINI_LIVE_MODEL", "gemini-3.8-live")
    max_live_sessions_per_case: int = int(os.getenv("MAX_LIVE_SESSIONS_PER_CASE", "2"))


settings = Settings()
