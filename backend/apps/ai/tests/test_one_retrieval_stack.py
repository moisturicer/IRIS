"""One retrieval stack, and one visibility predicate (IR-285).

`apps/ai/services/` held a second, record-level retrieval path: full-text
search over `Record.search_vector`, filtered by `publicly_visible()`. It was
narrower than the `visible_to(user)` predicate the rest of IRIS applies, so it
withheld rather than leaked — but two definitions of who-can-see-what drift,
and ADR-014 rejected keeping both for exactly that reason.

Deleting it is the easy half. The hard half is that it stays deleted: the way
this regresses is someone reaching for the familiar `publicly_visible()` in a
new retrieval module, or restoring a deleted file from git history because a
docstring still mentions it. Both are cheap to catch here and expensive to
notice in review.

No database and no Django settings — it reads files, like
`test_indexing_does_not_use_the_gateway.py`.
"""

import ast
import pathlib

APPS_AI = pathlib.Path(__file__).resolve().parents[1]
THIS_FILE = pathlib.Path(__file__).name

#: The modules IR-285 removed. Named rather than described, so a restored file
#: fails this test by its own name.
DELETED_MODULES = [
    "services/rag_pipeline.py",
    "services/retrieval.py",
    "services/llm_generator.py",
    "services/text_chunker.py",
    "services/vector_store.py",
    "services/summarizer.py",
]


def _python_files():
    return [
        path
        for path in APPS_AI.rglob("*.py")
        if path.name != THIS_FILE and "__pycache__" not in path.parts
    ]


def test_the_superseded_record_level_stack_is_gone():
    restored = [name for name in DELETED_MODULES if (APPS_AI / name).exists()]
    assert restored == [], (
        f"{restored} came back. The record-level pipeline was superseded by "
        f"`answers/service.py` and the retrieval package; a restored copy is a "
        f"second stack for someone to extend by mistake."
    )


def test_no_retrieval_path_uses_the_narrower_visibility_predicate():
    """`publicly_visible()` is the Discover catalogue's rule, not retrieval's.

    It stays in `apps/records/` — a public catalogue listing only published
    work is exactly what it is for. What must not come back is a *retrieval*
    result governed by it, because then what an answer cites depends on which
    of two predicates the code path happened to use.
    """
    offenders = [
        path.relative_to(APPS_AI).as_posix()
        for path in _python_files()
        if _references_publicly_visible(path)
    ]
    assert offenders == [], (
        f"{offenders} reach for the narrower predicate. Retrieval uses "
        f"`Record.objects.visible_to(user)`, applied before anything is scored."
    )


def test_related_works_still_ranks_through_the_one_predicate():
    """The caller this ticket migrated, guarded where it lives.

    `RecordViewSet.similar` was the last retrieval path on the narrower rule,
    and it sits in `apps/records/` — outside everything the check above scans.
    Scanning that whole app for `publicly_visible` would be wrong rather than
    thorough: it is the Discover catalogue's predicate and belongs there. So
    this looks at the one method, which is the one that regressed before.
    """
    views = APPS_AI.parent / "records" / "views.py"
    tree = ast.parse(views.read_text(encoding="utf-8"))
    similar = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "similar"
    )
    assert not any(
        isinstance(node, ast.Attribute) and node.attr == "publicly_visible"
        for node in ast.walk(similar)
    ), "related works is back on the narrower predicate (ADR-029 §7)"


def _references_publicly_visible(path: pathlib.Path) -> bool:
    """Whether this module reaches for the name in *code*, not in prose.

    Parsed rather than grepped, and that distinction is the whole reason this
    helper exists: every module that had the second predicate removed now
    carries a docstring explaining why it is not there, and a text search
    cannot tell an explanation from a use — it would fail on the very comments
    that make the decision survivable.

    It matches an attribute access, so `Record.objects.publicly_visible()` and
    a bare `qs.publicly_visible` both trip it, which is intended: a reference
    is a use waiting to happen. It would *not* catch `from ... import
    publicly_visible`, because that is not how a queryset method is reached
    and pretending otherwise would suggest a completeness this does not have.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return any(
        isinstance(node, ast.Attribute) and node.attr == "publicly_visible"
        for node in ast.walk(tree)
    )


def test_research_tools_reach_records_only_through_the_one_predicate():
    """ADR-038 §2.2: tools add no second visibility path (IR-500).

    `Record.objects` appears in one research module, whose function applies
    `visible_to(user)` before anything else touches the queryset.
    """
    research = APPS_AI / "research"
    reaching = {
        path.relative_to(research).as_posix()
        for path in research.rglob("*.py")
        if "tests" not in path.parts and _reaches_record_manager(path)
    }
    assert reaching == {"tools/common.py"}, (
        f"{sorted(reaching)} query Record directly; go through "
        f"`tools.common.readable_records`."
    )
    common = (research / "tools" / "common.py").read_text(encoding="utf-8")
    assert "Record.objects.visible_to(ctx.user)" in common


def _reaches_record_manager(path: pathlib.Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return any(
        isinstance(node, ast.Attribute)
        and node.attr == "objects"
        and isinstance(node.value, ast.Name)
        and node.value.id == "Record"
        for node in ast.walk(tree)
    )


#: What reaching the retrieval stack looks like from a module: the root's
#: accessors for it, and the calls a retriever is driven through.
_RETRIEVAL_CALLS = {
    "retriever", "answer_service", "source_selection", "embedder", "reranker",
    "retrieve", "embed_query", "rerank",
}


#: Only the value type `parse_citations` resolves against may be borrowed.
_ALLOWED_RETRIEVAL_IMPORT = "apps.ai.retrieval.ports."
_RETRIEVAL_MODULES = ("apps.ai.retrieval", "apps.ai.similarity", "apps.ai.keyword_index")


def _imported_names(node):
    """Fully qualified: `from a import b` is `a.b`."""
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if isinstance(node, ast.ImportFrom) and node.module:
        return [f"{node.module}.{alias.name}" for alias in node.names]
    return []


def test_the_overview_performs_no_retrieval():
    """The AI Overview reads the whole paper, not a ranked handful (IR-431)."""
    overview = APPS_AI / "overview"
    assert overview.is_dir() and not (APPS_AI / "overview.py").exists()

    offenders = []
    for path in overview.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            offenders += [
                f"{path.name}: imports {name}"
                for name in _imported_names(node)
                if name.startswith(_RETRIEVAL_MODULES)
                and not name.startswith(_ALLOWED_RETRIEVAL_IMPORT)
            ]
            if isinstance(node, ast.Attribute) and node.attr in _RETRIEVAL_CALLS:
                offenders.append(f"{path.name}: reaches .{node.attr}")
            if isinstance(node, ast.Name) and node.id == "OVERVIEW_TOP_K":
                offenders.append(f"{path.name}: OVERVIEW_TOP_K")
    assert offenders == [], offenders


def test_the_answer_service_offers_no_second_way_to_an_overview():
    """`answer_service(task=...)` existed only for the overview (IR-380)."""
    tree = ast.parse((APPS_AI / "composition.py").read_text(encoding="utf-8"))
    method = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "answer_service"
    )
    assert "task" not in [arg.arg for arg in method.args.args]
