from dataclasses import dataclass
import time
import json
import logging
import requests

from .config import Settings
from .crypto_sig import iso_timestamp_with_ms_utc, generate_signature_b64
from .logging_utils import format_response_text

@dataclass
class Token:
    jwe: str
    expires_at_epoch: float

class RuStoreTokenManager:
    def __init__(self, settings: Settings, logger: logging.Logger | None = None):
        self.settings = settings
        self._token: Token | None = None
        self.logger = logger

    def _valid(self) -> bool:
        if not self._token:
            return False
        return time.time() < (self._token.expires_at_epoch - self.settings.token_skew_seconds)

    def get_token(self, force_refresh: bool = False) -> str:
        if (not force_refresh) and self._valid():
            return self._token.jwe

        ts = iso_timestamp_with_ms_utc()
        signature = generate_signature_b64(self.settings.key_id, self.settings.private_key_b64, ts)

        url = f"{self.settings.base_url}/public/auth/"
        payload = {"keyId": self.settings.key_id, "timestamp": ts, "signature": signature}

        if self.logger:
            safe_payload = dict(payload)
            s = safe_payload.get("signature") or ""
            if s:
                safe_payload["signature"] = s[:16] + "..." + s[-16:]
            self.logger.info(
                "[AUTH][REQUEST] POST %s\npayload=%s",
                url,
                json.dumps(safe_payload, ensure_ascii=False),
            )

        try:
            r = requests.post(url, json=payload, timeout=self.settings.http_timeout_seconds)
            if self.logger:
                self.logger.info(
                    "[AUTH][RESPONSE] %s\nheaders=%s\nbody=%s",
                    r.status_code,
                    json.dumps(dict(r.headers), ensure_ascii=False),
                    format_response_text(r.text),
                )

            r.raise_for_status()
            data = r.json()
        except Exception as e:
            if self.logger:
                self.logger.exception("[AUTH][ERROR] %s: %s", type(e).__name__, e)
            raise

        body = data.get("body") or {}
        jwe = body.get("jwe")
        ttl = body.get("ttl")
        if not jwe or not ttl:
            raise RuntimeError(f"Неожиданный ответ auth: {data}")

        self._token = Token(jwe=jwe, expires_at_epoch=time.time() + float(ttl))
        return jwe
