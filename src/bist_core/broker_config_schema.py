from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

@dataclass(frozen=True)
class SchemaViolation:
    path: str
    message: str

def _type_ok(value: Any, t: str) -> bool:
    if t == "null":
        return value is None
    if t == "boolean":
        return isinstance(value, bool)
    if t == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if t == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if t == "string":
        return isinstance(value, str)
    if t == "array":
        return isinstance(value, list)
    if t == "object":
        return isinstance(value, dict)
    return True

def _validate(instance: Any, schema: dict, path: str = "$") -> list[SchemaViolation]:
    errs: list[SchemaViolation] = []

    if not isinstance(schema, dict):
        return errs

    if "anyOf" in schema and isinstance(schema["anyOf"], list):
        # valid if any branch has zero errors
        for sub in schema["anyOf"]:
            sub_errs = _validate(instance, sub, path)
            if not sub_errs:
                return []
        errs.append(SchemaViolation(path, "does not match anyOf schemas"))
        return errs

    if "type" in schema:
        t = schema["type"]
        if isinstance(t, list):
            if not any(_type_ok(instance, tt) for tt in t if isinstance(tt, str)):
                errs.append(SchemaViolation(path, f"type mismatch (expected one of {t})"))
                return errs
        elif isinstance(t, str):
            if not _type_ok(instance, t):
                errs.append(SchemaViolation(path, f"type mismatch (expected {t})"))
                return errs

    if isinstance(instance, dict):
        required = schema.get("required")
        if isinstance(required, list):
            for k in required:
                if isinstance(k, str) and k not in instance:
                    errs.append(SchemaViolation(f"{path}.{k}", "missing required property"))

        props = schema.get("properties")
        if isinstance(props, dict):
            for k, sub_schema in props.items():
                if k in instance:
                    errs.extend(_validate(instance[k], sub_schema, f"{path}.{k}"))

        ap = schema.get("additionalProperties")
        if ap is False and isinstance(props, dict):
            for k in instance.keys():
                if k not in props:
                    errs.append(SchemaViolation(f"{path}.{k}", "additional property not allowed"))

    if isinstance(instance, list):
        items = schema.get("items")
        if isinstance(items, dict):
            for i, v in enumerate(instance):
                errs.extend(_validate(v, items, f"{path}[{i}]"))

    return errs

def load_schema(schema_path: Path) -> dict:
    return json.loads(schema_path.read_text(encoding="utf-8"))

def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))

def validate_broker_config(config: Any, schema: dict) -> list[SchemaViolation]:
    return _validate(config, schema, "$")

def validate_broker_config_file(config_path: Path, schema_path: Path) -> list[SchemaViolation]:
    cfg = load_json(config_path)
    sch = load_schema(schema_path)
    return validate_broker_config(cfg, sch)
