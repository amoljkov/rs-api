from typing import Any, Dict, Tuple
import json
import logging
import time
import requests

from .config import Settings
from .token_manager import RuStoreTokenManager
from .logging_utils import format_json_for_log, format_response_text

class RuStoreApiClient:
    def __init__(self, settings: Settings, token_manager: RuStoreTokenManager, logger: logging.Logger | None = None):
        self.settings = settings
        self.tm = token_manager
        self.logger = logger
        self.session = requests.Session()

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
            self.logger.info(
                "[API][REQUEST] %s %s\nheaders=%s\nparams=%s\nbody=%s",
                http_method,
                url,
                json.dumps(safe_headers, ensure_ascii=False),
                json.dumps(qp, ensure_ascii=False),
                format_json_for_log(body) if body else None,
            )

        resp = self._request_with_retries(
            http_method,
            url,
            headers=headers,
            params=qp,
            json=body if body else None,
        )

        # если токен протух — ретрай с force_refresh
        if resp.status_code in (401, 403):
            token2 = self.tm.get_token(force_refresh=True)
            headers["Public-Token"] = token2
            resp = self._request_with_retries(
                http_method,
                url,
                headers=headers,
                params=qp,
                json=body if body else None,
            )

        if self.logger:
            self.logger.info(
                "[API][RESPONSE] %s\nheaders=%s\nbody=%s",
                resp.status_code,
                json.dumps(dict(resp.headers), ensure_ascii=False),
                format_response_text(resp.text),
            )

        return resp, url

    def _request_with_retries(self, http_method: str, url: str, **kwargs) -> requests.Response:
        retries = 3
        backoff = 0.5
        last_exc = None
        for attempt in range(retries):
            try:
                resp = self.session.request(
                    http_method,
                    url,
                    timeout=self.settings.http_timeout_seconds,
                    **kwargs,
                )
            except requests.RequestException as exc:
                last_exc = exc
                if attempt < retries - 1:
                    time.sleep(backoff)
                    backoff *= 2
                    continue
                raise
            if resp.status_code in (429, 500, 502, 503, 504) and attempt < retries - 1:
                time.sleep(backoff)
                backoff *= 2
                continue
            return resp
        if last_exc:
            raise last_exc
        return resp
