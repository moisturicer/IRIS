"""Tool-argument validation against each tool's JSON Schema (IR-500)."""

import pytest

from apps.ai.research.schema import ArgumentsRejected, check_schema, validate

SCHEMA = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "minLength": 1, "maxLength": 10},
        "k": {"type": "integer", "minimum": 1, "maximum": 10},
        "records": {"type": "array", "items": {"type": "string", "maxLength": 12}, "maxItems": 2},
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


@pytest.mark.parametrize("unbounded", [
    {"type": "string"},
    {"type": "integer", "minimum": 1},
    {"type": "integer", "maximum": 9},
    {"type": "array", "items": {"type": "string", "maxLength": 5}},
    {"type": "array", "maxItems": 3, "items": {"type": "string"}},
])
def test_every_parameter_is_bounded_at_declaration(unbounded):
    # IR-590: a model cannot send an unbounded string, number or list.
    with pytest.raises(ValueError, match="unbounded"):
        check_schema({"type": "object", "properties": {"x": unbounded},
                      "additionalProperties": False})


@pytest.mark.parametrize("name", ["valid", "paid_only", "grid", "record", "records"])
def test_words_ending_in_id_letters_are_not_raw_ids(name):
    check_schema({"type": "object", "additionalProperties": False,
                  "properties": {name: {"type": "boolean"}}})


def test_an_enum_bounds_a_string():
    check_schema({"type": "object", "additionalProperties": False,
                  "properties": {"x": {"type": "string", "enum": ["a"]}}})


@pytest.mark.parametrize("name", [
    "user", "identity", "scope", "scope_record_id", "conversation_id", "deadline",
    "spend", "budget", "run_id", "permits", "lane", "source_policy",
    "id", "ids", "pk", "record_id", "record_ids", "sql", "raw_sql",
    "recordId", "uuid", "record_uuid", "identifier",
])
def test_injected_context_and_raw_ids_are_never_parameters(name):
    # The application injects identity, scope, deadline and spend (IR-590).
    with pytest.raises(ValueError, match="reserved"):
        check_schema({"type": "object", "additionalProperties": False,
                      "properties": {name: {"type": "integer", "minimum": 1, "maximum": 9}}})


def test_every_run_context_field_is_reserved():
    from dataclasses import fields

    from apps.ai.research.context import RunContext
    from apps.ai.research.schema import RESERVED

    assert {f.name for f in fields(RunContext)} <= RESERVED
