from dataclasses import dataclass
from dotenv import load_dotenv
from .resource import app_dir
import os
from urllib.parse import urlparse

load_dotenv(os.path.join(app_dir(), ".env"))

@dataclass(frozen=True)
class Settings:
    base_url: str = os.getenv("RUSTORE_BASE_URL", "https://public-api.rustore.ru").rstrip("/")
    key_id: str = os.getenv("RUSTORE_KEY_ID", "")
    private_key_b64: str = os.getenv("RUSTORE_PRIVATE_KEY_B64", "")
    token_skew_seconds: int = int(os.getenv("RUSTORE_TOKEN_SKEW_SECONDS", "30"))
    http_timeout_seconds: int = int(os.getenv("HTTP_TIMEOUT_SECONDS", "30"))

def get_settings() -> Settings:
    s = Settings()
    allow_insecure = os.getenv("RUSTORE_ALLOW_INSECURE_URL", "").strip() in ("1", "true", "yes")
    parsed = urlparse(s.base_url)
    if not allow_insecure:
        if parsed.scheme != "https" or not parsed.netloc:
            raise RuntimeError("RUSTORE_BASE_URL должен быть https и содержать корректный хост")
    if not s.key_id or not s.private_key_b64:
        raise RuntimeError("Не заданы RUSTORE_KEY_ID / RUSTORE_PRIVATE_KEY_B64 в .env")
    return s
