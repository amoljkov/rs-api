from typing import Any, Dict, Tuple
import json
import requests

from .config import Settings
from .token_manager import RuStoreTokenManager

class RuStoreApiClient:
    def __init__(self, settings: Settings, token_manager: RuStoreTokenManager, logger=None):
        self.settings = settings
        self.tm = token_manager
        self.logger = logger  # callable(str) | None

    def call(
        self,
        http_method: str,
        path_template: str,
        *,
        path_params: Dict[str, Any],
        query_params: Dict[str, Any],
        body: Dict[str, Any] | None
    ) -> Tuple[requests.Response, str]:
        token = self.tm.get_token()

        path = path_template.format(**path_params)
        url = f"{self.settings.base_url}{path}"

        headers = {
            "Public-Token": token,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        qp = {k: v for k, v in (query_params or {}).items() if v not in (None, "", [])}

        if self.logger:
            safe_headers = dict(headers)
            if "Public-Token" in safe_headers and safe_headers["Public-Token"]:
                safe_headers["Public-Token"] = safe_headers["Public-Token"][:20] + "...(redacted)"
            self.logger(
                f"[API][REQUEST] {http_method} {url}\n"
                f"headers={json.dumps(safe_headers, ensure_ascii=False)}\n"
                f"params={json.dumps(qp, ensure_ascii=False)}\n"
                f"body={json.dumps(body, ensure_ascii=False) if body else None}\n"
            )

        resp = requests.request(
            http_method, url,
            headers=headers,
            params=qp,
            json=body if body else None,
            timeout=self.settings.http_timeout_seconds,
        )

        # если токен протух — ретрай с force_refresh
        if resp.status_code in (401, 403):
            token2 = self.tm.get_token(force_refresh=True)
            headers["Public-Token"] = token2
            resp = requests.request(
                http_method, url,
                headers=headers,
                params=qp,
                json=body if body else None,
                timeout=self.settings.http_timeout_seconds,
            )

        if self.logger:
            self.logger(
                f"[API][RESPONSE] {resp.status_code}\n"
                f"headers={json.dumps(dict(resp.headers), ensure_ascii=False)}\n"
                f"body={resp.text}\n"
            )

        return resp, url