"""Central configuration, read from environment variables (12-factor style)."""
import os


def _bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).lower() in {"1", "true", "yes", "on"}


class Settings:
    APP_NAME = "RaktaSetu"
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./raktasetu.db")
    REDIS_URL = os.getenv("REDIS_URL", "")  # optional; falls back to in-memory store
    ML_SERVICE_URL = os.getenv("ML_SERVICE_URL", "http://localhost:8001")
    JWT_SECRET = os.getenv("JWT_SECRET", "dev-only-insecure-secret-change-me-in-production")
    JWT_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "24"))
    # DEMO_MODE returns the OTP in the API response so the expo demo works without an SMS gateway
    DEMO_MODE = _bool("DEMO_MODE", "true")
    ADMIN_PHONES = {p.strip() for p in os.getenv("ADMIN_PHONES", "9999999999").split(",") if p.strip()}
    # Escalation timings (seconds) - short defaults so the live demo shows escalation quickly
    RESPONSE_WINDOW_SEC = int(os.getenv("RESPONSE_WINDOW_SEC", "120"))
    COMMITMENT_WINDOW_MIN = int(os.getenv("COMMITMENT_WINDOW_MIN", "90"))
    ESCALATION_TICK_SEC = int(os.getenv("ESCALATION_TICK_SEC", "10"))
    SEARCH_RADII_KM = [5, 10, 25, 50]
    DONORS_PER_WAVE = int(os.getenv("DONORS_PER_WAVE", "3"))
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")  # optional real phone notifications
    SEED_DEMO_DATA = _bool("SEED_DEMO_DATA", "true")
    STATIC_DIR = os.getenv("STATIC_DIR", "")  # serve frontend from the API (local dev only)
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")


settings = Settings()
