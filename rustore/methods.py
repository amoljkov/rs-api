from dataclasses import dataclass
from typing import Any, Dict
import yaml

from .resource import external_or_embedded

@dataclass(frozen=True)
class MethodDef:
    group_key: str
    group_title: str
    key: str
    title: str
    http_method: str
    paths: Dict[str, str]                 # prod/sandbox
    params: Dict[str, Dict[str, Any]]     # path/query/body

def load_all(path: str = "methods.yaml") -> Dict[str, Any]:
    real_path = external_or_embedded(path)
    with open(real_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def list_methods(cfg: Dict[str, Any]) -> list[MethodDef]:
    out: list[MethodDef] = []
    groups = cfg.get("groups", {}) or {}
    for gk, gv in groups.items():
        gt = gv.get("title", gk)
        methods = gv.get("methods", {}) or {}
        for mk, mv in methods.items():
            out.append(MethodDef(
                group_key=gk,
                group_title=gt,
                key=mk,
                title=mv.get("title", mk),
                http_method=mv.get("http_method", "GET").upper(),
                paths=mv.get("paths", {}) or {},
                params=mv.get("params", {"path": {}, "query": {}, "body": {}}) or {},
            ))
    return out