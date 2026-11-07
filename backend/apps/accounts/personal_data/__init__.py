"""
A person's own copy of their data (ADR-051 decision 13, IR-786).

`build_export(user)` returns one JSON-ready dict. `registry` is the list the
export is held to: every model that points at a person is declared there as
included (under a section) or excluded (with a reason), and a test fails when
one is not.
"""

from .export import EXPORT_FORMAT, SECTIONS, build_export

__all__ = ["EXPORT_FORMAT", "SECTIONS", "build_export"]
