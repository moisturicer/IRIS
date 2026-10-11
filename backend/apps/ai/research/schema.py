"""Validates model-written arguments against the JSON Schema subset tools declare."""

from __future__ import annotations

import json
from typing import Any, Mapping

_SUPPORTED = {
    "type", "properties", "required", "additionalProperties", "items",
    "minLength", "maxLength", "minimum", "maximum", "maxItems", "enum",
    "description",
}


class ArgumentsRejected(ValueError):
    """Arguments the schema does not admit. The message is a reason code."""


def check_schema(schema: Mapping[str, Any]) -> None:
    """Raise if `schema` uses a keyword `validate` does not enforce."""
    unknown = set(schema) - _SUPPORTED
    if unknown:
        raise ValueError(f"unsupported schema keywords: {sorted(unknown)}")
    if schema.get("type") == "object" and schema.get("additionalProperties") is not False:
        raise ValueError("an object schema must set additionalProperties: false")
    for child in schema.get("properties", {}).values():
        check_schema(child)
    if "items" in schema:
        check_schema(schema["items"])


def validate(arguments: Any, schema: Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments) if arguments.strip() else {}
        except json.JSONDecodeError:
            raise ArgumentsRejected("malformed_json") from None
    if not isinstance(arguments, dict):
        raise ArgumentsRejected("not_an_object")

    properties = schema.get("properties", {})
    if set(arguments) - set(properties):
        raise ArgumentsRejected("unknown_argument")
    for name in schema.get("required", ()):
        if name not in arguments:
            raise ArgumentsRejected("missing_argument")
    for name, value in arguments.items():
        _check(value, properties[name])
    return dict(arguments)


def _check(value: Any, schema: Mapping[str, Any]) -> None:
    kind = schema["type"]
    if kind == "string":
        if not isinstance(value, str):
            raise ArgumentsRejected("wrong_type")
        if len(value.strip()) < schema.get("minLength", 0):
            raise ArgumentsRejected("too_short")
        if len(value) > schema.get("maxLength", len(value)):
            raise ArgumentsRejected("too_long")
    elif kind == "integer":
        # `bool` is an `int` in Python; JSON says it is not.
        if not isinstance(value, int) or isinstance(value, bool):
            raise ArgumentsRejected("wrong_type")
        if value < schema.get("minimum", value) or value > schema.get("maximum", value):
            raise ArgumentsRejected("out_of_range")
    elif kind == "boolean":
        if not isinstance(value, bool):
            raise ArgumentsRejected("wrong_type")
    elif kind == "array":
        if not isinstance(value, list):
            raise ArgumentsRejected("wrong_type")
        if len(value) > schema.get("maxItems", len(value)):
            raise ArgumentsRejected("too_many_items")
        for item in value:
            _check(item, schema["items"])
    else:
        raise ValueError(f"unsupported type {kind!r}")
    if "enum" in schema and value not in schema["enum"]:
        raise ArgumentsRejected("not_in_enum")
