import os
from typing import Optional
from dotenv import load_dotenv
from pydantic_settings import BaseSettings

# Load environment variables from .env
load_dotenv()

def get_initial_fns_key() -> str:
    env_key = os.getenv("FNS_API_KEY", "")
    if env_key:
        return env_key.strip()
    fns_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "fns_key.txt")
    if os.path.exists(fns_file):
        try:
            with open(fns_file, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            pass
    return ""

class Settings(BaseSettings):
    PROJECT_NAME: str = "Кассовый радар Центр-Инвест"
    VERSION: str = "0.1.0-hack2026"
    API_PREFIX: str = "/api"
    
    # Modern SQL Database - SQLite default, PostgreSQL ready
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./radar.db")
    
    # Forecasting
    DEFAULT_HORIZON: int = 30
    MAX_HORIZON: int = 90
    CORRIDOR_FACTOR: float = 1.28  # P10 to P90 for standard normal
    
    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "centroinvest-hack2026-secret-key-12345")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 1 day
    
    # Data directory
    DATA_DIR: str = os.getenv("DATA_DIR", "./data")
    
    # SMTP Email Settings (Yandex SSL)
    SMTP_HOST: str = os.getenv("SMTP_HOST", "smtp.yandex.ru")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", 465))
    SMTP_USER: str = os.getenv("SMTP_USER", "lebedev.andrey1303@yandex.ru")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "qwufrmrepifeebjx")
    SMTP_FROM_NAME: str = os.getenv("SMTP_FROM_NAME", "Банк Центр-инвест • Кассовый радар")
    
    # FNS API (api-fns.ru)
    FNS_API_KEY: str = get_initial_fns_key()

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True

settings = Settings()
