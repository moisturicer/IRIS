"""Tool-argument validation against each tool's JSON Schema (IR-500)."""

import pytest

from apps.ai.research.schema import ArgumentsRejected, check_schema, validate

SCHEMA = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "minLength": 1, "maxLength": 10},
        "k": {"type": "integer", "minimum": 1, "maximum": 10},
        "records": {"type": "array", "items": {"type": "string"}, "maxItems": 2},
        "group_by": {"type": "string", "enum": ["year", "classification"]},
        "is_ip": {"type": "boolean"},
    },
    "required": ["query"],
    "additionalProperties": False,
}


def test_valid_arguments_come_back_as_a_dict():
    assert validate({"query": "x", "k": 3}, SCHEMA) == {"query": "x", "k": 3}


def test_a_json_string_is_parsed():
    assert validate('{"query": "x"}', SCHEMA) == {"query": "x"}


@pytest.mark.parametrize(
    "arguments",
    [
        "not json",
        "[1, 2]",
        {},
        {"query": ""},
        {"query": "x" * 11},
        {"query": "x", "k": 0},
        {"query": "x", "k": 11},
        {"query": "x", "k": "3"},
        {"query": "x", "k": True},
        {"query": "x", "records": ["R1", "R2", "R3"]},
        {"query": "x", "records": [1]},
        {"query": "x", "group_by": "owner"},
        {"query": "x", "is_ip": "yes"},
        {"query": "x", "user": 1},
        {"query": "x", "scope_record_id": 4},
    ],
)
def test_anything_outside_the_schema_is_rejected(arguments):
    with pytest.raises(ArgumentsRejected):
        validate(arguments, SCHEMA)


def test_a_schema_that_admits_extra_arguments_is_refused_at_declaration():
    check_schema(SCHEMA)
    with pytest.raises(ValueError):
        check_schema({"type": "object", "properties": {}})
    with pytest.raises(ValueError):
        check_schema({**SCHEMA, "pattern": "x"})
