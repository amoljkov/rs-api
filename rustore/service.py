from typing import Any, Dict, Tuple
import requests

from .api_client import RuStoreApiClient
from .methods import MethodDef


class RuStoreService:
    def __init__(self, client: RuStoreApiClient):
        self.client = client

    def call_method(
        self,
        method: MethodDef,
        env: str,
        *,
        path_params: Dict[str, Any],
        query_params: Dict[str, Any],
        body: Dict[str, Any] | None,
    ) -> Tuple[requests.Response, str]:
        path_template = (method.paths or {}).get(env)
        if not path_template:
            raise ValueError(f"Для окружения '{env}' не задан путь в methods.yaml")
        return self.client.call(
            method.http_method,
            path_template,
            path_params=path_params,
            query_params=query_params,
            body=body,
        )
