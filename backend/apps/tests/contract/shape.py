"""
The structure of a JSON response, and what changed between two (IR-915).

Pure: no Django, no database. The contract test records what an endpoint
answers, and this module says whether a later answer still has the same
*structure*. Values are never compared: an id, a timestamp or a title differs
between runs, and a check that failed on them would fail on nothing a screen
depends on.

A structure is one of

    "null" | "boolean" | "number" | "string"
    {"array": <structure> | None}          None: the sample list was empty
    {"object": {key: <structure>}, "optional": [key, ...]}
                                           "optional": keys only some list items carry
    {"mixed": [<structure>, ...]}          a list whose items differ in kind

What a change means for a screen that reads the response:

* a field **removed**, or its kind **changed** (a string that is now a number,
  or a value that is now `null`): the screen can break, so it FAILS;
* a field **added**: an older screen ignores it, so it is only reported. Failing
  here would make every backend field addition wait on a fixture refresh, the
  coupling IR-913 removed from the Audit Log;
* a field that is `null` in the sample says only that the key exists: whatever
  the sample world holds for an optional field is not a promise about its type.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

#: How many items of a list a stored sample keeps.
SAMPLE_ITEMS = 3


def shape_of(value: Any) -> Any:
    """The structure of one JSON value."""
    if value is None:
        return "null"
    if isinstance(value, bool):  # before int: bool is an int in Python
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        items: Any = None
        for item in value:
            items = merge(items, shape_of(item))
        return {"array": items}
    if isinstance(value, dict):
        return {"object": {key: shape_of(item) for key, item in value.items()}}
    raise TypeError(f"{type(value).__name__} is not a JSON value")


def merge(left: Any, right: Any) -> Any:
    """
    One structure for two list items, so a field an item leaves `null` is typed
    by another item that fills it. `None` is "no item yet".
    """
    if left is None:
        return right
    if right is None or left == right:
        return left
    if left == "null":
        return right
    if right == "null":
        return left
    if isinstance(left, dict) and isinstance(right, dict):
        if "object" in left and "object" in right:
            before, after = left["object"], right["object"]
            # A key only some items carry is optional: a union of two shapes,
            # such as an available and an unavailable saved paper.
            optional = (
                set(left.get("optional", ())) | set(right.get("optional", ()))
                | (set(before) ^ set(after))
            )
            merged: dict[str, Any] = {"object": {
                key: merge(before.get(key), after.get(key)) for key in {**before, **after}
            }}
            if optional:
                merged["optional"] = sorted(optional)
            return merged
        if "array" in left and "array" in right:
            return {"array": merge(left["array"], right["array"])}
    alternatives = []
    for side in (left, right):
        for part in side["mixed"] if isinstance(side, dict) and "mixed" in side else [side]:
            if part not in alternatives:
                alternatives.append(part)
    return {"mixed": alternatives}


def sample_of(value: Any) -> Any:
    """What the fixture keeps of a response: its values, with long lists cut."""
    if isinstance(value, list):
        return [sample_of(item) for item in value[:SAMPLE_ITEMS]]
    if isinstance(value, dict):
        return {key: sample_of(item) for key, item in value.items()}
    return value


@dataclass
class Diff:
    #: Changes a screen can break on, each naming the field.
    breaking: list[str] = field(default_factory=list)
    #: Fields the response gained.
    added: list[str] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.breaking or self.added)


def _kind(structure: Any) -> str:
    if isinstance(structure, str):
        return structure
    return next(iter(structure))


def compare(expected: Any, actual: Any, path: str = "$") -> Diff:
    """What changed from the recorded structure to the one an endpoint answers now."""
    diff = Diff()
    _compare(expected, actual, path, diff)
    return diff


def _compare(expected: Any, actual: Any, path: str, diff: Diff) -> None:
    if expected is None or actual is None:
        return  # an empty sample list says nothing about its items
    if expected == "null":
        return  # the key existed; its kind was never shown
    if actual == "null":
        diff.breaking.append(f"{path}: was {_describe(expected)}, now null")
        return
    if isinstance(expected, dict) and "mixed" in expected:
        if not _fits(expected["mixed"], actual):
            diff.breaking.append(f"{path}: was {_describe(expected)}, now {_describe(actual)}")
        return
    if _kind(expected) != _kind(actual):
        diff.breaking.append(f"{path}: was {_describe(expected)}, now {_describe(actual)}")
        return
    if isinstance(expected, dict) and "object" in expected:
        before, after = expected["object"], actual["object"]
        optional = expected.get("optional", ())
        for key in before:
            if key not in after:
                if key not in optional:
                    diff.breaking.append(f"{path}.{key}: removed")
            else:
                _compare(before[key], after[key], f"{path}.{key}", diff)
        diff.added.extend(f"{path}.{key}: added" for key in after if key not in before)
    elif isinstance(expected, dict) and "array" in expected:
        _compare(expected["array"], actual["array"], f"{path}[]", diff)


def _fits(alternatives: list[Any], actual: Any) -> bool:
    return any(not compare(option, actual).breaking for option in alternatives)


def _describe(structure: Any) -> str:
    if isinstance(structure, str):
        return structure
    kind = _kind(structure)
    if kind == "mixed":
        return " or ".join(_describe(option) for option in structure["mixed"])
    return {"object": "an object", "array": "a list"}[kind]
