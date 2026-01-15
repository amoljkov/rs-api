def build_body_template(body_schema: dict) -> dict:
    """
    Builds a valid JSON template from methods.yaml -> params.body schema.
    Values are placeholders so user can fill them.

    Rules:
    - str -> ""
    - int/float/bool -> null (None in Python)
    - list[...] -> []
    - dict/object/json -> {}
    - unknown -> null
    """
    if not body_schema:
        return {}

    out = {}
    for key, meta in body_schema.items():
        if meta is None:
            out[key] = None
            continue

        t = (meta.get("type") or "str").strip()

        if t == "str":
            out[key] = ""
        elif t in ("int", "float", "bool"):
            out[key] = None
        elif t.startswith("list[") and t.endswith("]"):
            out[key] = []
        elif t in ("dict", "object", "json"):
            out[key] = {}
        else:
            out[key] = None

    return out


def parse_typed(raw: str, type_name: str):
    if raw is None or raw == "":
        return None
    t = (type_name or "str").strip()
    if t == "int":
        return int(raw)
    if t == "float":
        return float(raw)
    if t == "bool":
        return raw.strip().lower() in ("1", "true", "yes", "y", "on")
    if t.startswith("list[") and t.endswith("]"):
        inner = t[5:-1].strip()
        items = [x.strip() for x in raw.split(",") if x.strip()]
        if inner == "int":
            return [int(x) for x in items]
        return items
    return raw