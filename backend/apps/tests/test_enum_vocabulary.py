"""
IR-135: the workflow vocabulary is defined once, in `core.enums`.

Three guarantees, and they fail for different reasons:

1. **The enums match the database.** Every `TextChoices` value equals what the
   corresponding model field actually stores. This is what makes the refactor a
   source-only change -- if someone "tidies" `rdco_intake` to `intake`, this
   fails before a migration is ever written.

2. **No bare vocabulary literal remains in application source.** The scan is
   AST-based rather than textual, so a status word appearing in a comment or a
   docstring is not a finding -- only an actual string constant is. That matters
   here because these modules are heavily commented and half the prose mentions
   the statuses by name.

3. **`ktto_review` is absent.** It was already absent when IR-135 started (the
   grep returned nothing); this pins it so it cannot come back. The frontend's
   `StatusBadge.tsx` still carries the key, which is the drift that prompted the
   ticket -- out of scope here, since labels come from the API (P1-05).

The scan deliberately skips migrations and tests. **Migrations are frozen
history**: a data migration that wrote `"approved"` in April must keep saying
`"approved"`, because it describes what happened then, and CLAUDE.md forbids
editing an applied migration anyway. **Tests keep their literals on purpose**:
a test asserting `response.data["pipeline_status"] == "draft"` is pinning the
wire format, and rewriting it to `PipelineStatus.DRAFT` would make it pass
through any future rename -- exactly the regression this suite should catch.
"""

import ast
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, TestCase

from core.enums import (
    ClearanceStatus,
    IPType,
    Office,
    PipelineStatus,
    PUBLICLY_VISIBLE_STATUSES,
    RecordTypeName,
    RequestStatus,
    ReviewDecision,
    ReviewStage,
    RoleName,
)

APPS_DIR = Path(settings.BASE_DIR) / "apps"

#: Every enum whose values must not appear as bare literals in app source.
GOVERNED_ENUMS = (
    PipelineStatus,
    ReviewStage,
    ReviewDecision,
    ClearanceStatus,
    Office,
    RequestStatus,
    IPType,
    RecordTypeName,
    RoleName,
)

GOVERNED_VALUES = {str(member.value) for enum in GOVERNED_ENUMS for member in enum}

#: Sites where a bare literal is correct and must stay. Each entry needs a
#: reason -- an allowlist without one is just a silenced test.
ALLOWED = {
    # (IR-227) Replaces the entry for the deleted `seed_test_users.py`. Every
    # *workflow* value in this seeder is an enum member -- it drives the real
    # services, so it has to be. The two literals here are the demo students'
    # **surnames**: "Sam Student" and "Ana Adviser", carried over from the
    # seed_demo_users.py script this command absorbed, so the logins keep
    # reading the way people already know them. Same shape as the
    # embedding_space.py entry below: two concepts, one string. Renaming the
    # humans to satisfy a workflow guard would be the tail wagging the dog.
    "records/management/commands/seed_demo.py",
    # Declares its own `EmbeddingSpaceStatus` for a backfill state machine
    # (pending/active/retired). The word "pending" collides with
    # RequestStatus.PENDING and means something unrelated -- an embedding space
    # awaiting backfill, not a person's request awaiting a decision. Two
    # concepts, one string; pointing this file at core.enums would be wrong.
    "ai/models/embedding_space.py",
    # "pending", "approved" and "declined" here are URL path segments and DRF
    # action method names (`as_view({"get": "approved"})`), not stored values.
    # They are the router's vocabulary, not the workflow's.
    "reviews/urls.py",
}


def _is_docstring_node(node, parents):
    """True when this string constant is a module/class/function docstring."""
    parent = parents.get(id(node))
    if not isinstance(parent, ast.Expr):
        return False
    grandparent = parents.get(id(parent))
    if not isinstance(grandparent, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
        return False
    return grandparent.body and grandparent.body[0] is parent


#: Assignment targets whose string members name *model fields*, not values.
FIELD_LIST_TARGETS = {
    "fields", "read_only_fields", "exclude", "ordering", "ordering_fields",
    "search_fields", "filterset_fields", "list_display", "list_filter",
}

#: Queryset methods whose string arguments are field paths, not values.
FIELD_PATH_CALLS = {
    "select_related", "prefetch_related", "only", "defer",
    "values", "values_list", "order_by", "distinct",
}


def _ancestors(node, parents, limit=6):
    seen = []
    current = parents.get(id(node))
    while current is not None and len(seen) < limit:
        seen.append(current)
        current = parents.get(id(current))
    return seen


def _is_orm_field_path(node, parents):
    """
    True when this string names a model field rather than a stored value.

    `"adviser"` is both `ReviewStage.ADVISER` and a `Record` field, and
    `fields = ("adviser", "added_by", ...)` means the latter. Rewriting those to
    `ReviewStage.ADVISER` would be actively wrong -- it happens to produce the
    same string, so nothing would break until someone relabelled the stage and
    the serializer quietly started asking for a field that does not exist.
    Field paths and stored values are two namespaces that share spellings.
    """
    for ancestor in _ancestors(node, parents):
        if isinstance(ancestor, ast.Assign):
            for target in ancestor.targets:
                if isinstance(target, ast.Name) and target.id in FIELD_LIST_TARGETS:
                    return True
        if isinstance(ancestor, ast.keyword) and ancestor.arg == "update_fields":
            return True
        if isinstance(ancestor, ast.Call):
            func = ancestor.func
            if isinstance(func, ast.Attribute) and func.attr in FIELD_PATH_CALLS:
                return True
    return False


def _bare_vocabulary_literals(path):
    """Every governed value appearing as a real string constant in `path`."""
    tree = ast.parse(path.read_text(encoding="utf-8"))

    parents = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[id(child)] = parent

    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if node.value not in GOVERNED_VALUES:
            continue
        if _is_docstring_node(node, parents):
            continue
        if _is_orm_field_path(node, parents):
            continue
        found.append((node.lineno, node.value))
    return found


def _scanned_files():
    for path in sorted(APPS_DIR.rglob("*.py")):
        rel = path.relative_to(APPS_DIR).as_posix()
        if "/migrations/" in f"/{rel}":
            continue
        if "test" in path.name or "/tests/" in f"/{rel}":
            continue
        if rel in ALLOWED:
            continue
        yield rel, path


class VocabularyIsSingleSourcedTests(SimpleTestCase):
    """No module may spell a workflow value out by hand."""

    def test_no_bare_vocabulary_literals_in_app_source(self):
        offenders = {}
        for rel, path in _scanned_files():
            found = _bare_vocabulary_literals(path)
            if found:
                offenders[rel] = found

        self.assertEqual(
            offenders, {},
            "bare workflow literals remain -- import the value from core.enums "
            f"instead:\n{_format(offenders)}",
        )

    def test_the_scan_actually_scans_something(self):
        """
        A guard on the guard. If the walk stops finding files -- a moved `apps/`
        directory, a changed BASE_DIR -- the test above passes vacuously, which
        is the failure mode that made a green suite meaningless twice before
        (IR-163, IR-165).
        """
        scanned = list(_scanned_files())
        self.assertGreater(len(scanned), 30, "the vocabulary scan found almost no files to read")
        self.assertGreater(len(GOVERNED_VALUES), 30, "the governed vocabulary looks truncated")

    def test_ktto_review_is_absent_from_live_backend_code(self):
        """
        Never a current backend value. It survives in the frontend's StatusBadge
        map, which is the drift IR-135 was written from.

        **Migrations are exempt and must stay exempt.** `records/0001_initial`
        names `ktto_review` in its `choices` because that is what the field
        genuinely looked like when the migration was written. History is a
        record of what was, not a place to assert what should be, and CLAUDE.md
        forbids editing an applied migration. Excluding them is the point of
        this test, not a hole in it.
        """
        self.assertNotIn("ktto_review", {str(s.value) for s in PipelineStatus})

        hits = []
        for path in sorted(Path(settings.BASE_DIR).rglob("*.py")):
            rel = path.relative_to(settings.BASE_DIR).as_posix()
            if "/migrations/" in f"/{rel}":
                continue
            # Tests too, and this file most of all: it has to name the value it
            # is banning in order to ban it.
            if "test" in path.name or "/tests/" in f"/{rel}":
                continue
            if "ktto_review" in path.read_text(encoding="utf-8"):
                hits.append(rel)
        self.assertEqual(hits, [], f"'ktto_review' is back in live backend code: {hits}")


class EnumsMatchTheDatabaseTests(TestCase):
    """
    The values are the stored values. IR-135 renames nothing, and this is what
    proves it -- read off the model fields rather than restated by hand.
    """

    def test_pipeline_status_choices_come_from_the_enum(self):
        from apps.records.models import Record

        field = Record._meta.get_field("pipeline_status")
        self.assertEqual(list(field.choices), list(PipelineStatus.choices))
        self.assertEqual(field.default, PipelineStatus.DRAFT)

    def test_review_choices_come_from_the_enums(self):
        from apps.reviews.models import Review

        self.assertEqual(
            list(Review._meta.get_field("stage").choices), list(ReviewStage.choices)
        )
        self.assertEqual(
            list(Review._meta.get_field("status").choices), list(ReviewDecision.choices)
        )

    def test_clearance_choices_come_from_the_enums(self):
        from apps.reviews.models import RecordClearance

        self.assertEqual(
            list(RecordClearance._meta.get_field("office").choices), list(Office.choices)
        )
        self.assertEqual(
            list(RecordClearance._meta.get_field("status").choices), list(ClearanceStatus.choices)
        )
        self.assertEqual(
            RecordClearance._meta.get_field("status").default, ClearanceStatus.PENDING
        )

    def test_request_status_is_shared_by_all_three_request_models(self):
        from apps.accounts.models import RoleRequest
        from apps.records.models import DeleteRequest, DownloadRequest

        for model in (DownloadRequest, DeleteRequest, RoleRequest):
            with self.subTest(model=model.__name__):
                field = model._meta.get_field("status")
                self.assertEqual(list(field.choices), list(RequestStatus.choices))
                self.assertEqual(field.default, RequestStatus.PENDING)

    def test_ip_type_choices_come_from_the_enum(self):
        from apps.records.models import Record

        self.assertEqual(
            list(Record._meta.get_field("ip_type").choices), list(IPType.choices)
        )

    def test_publicly_visible_statuses_are_pipeline_statuses(self):
        """
        The tuple IR-153's visibility predicate filters on. It must stay a subset
        of the pipeline vocabulary -- a typo here silently empties Discover.
        """
        self.assertTrue(set(PUBLICLY_VISIBLE_STATUSES) <= {s.value for s in PipelineStatus})
        self.assertEqual(len(PUBLICLY_VISIBLE_STATUSES), 3)

    def test_seeded_role_names_exist(self):
        """`RoleName` claims to mirror rows migration accounts/0003 seeds."""
        from apps.accounts.models import Role

        seeded = set(Role.objects.values_list("name", flat=True))
        missing = {r.value for r in RoleName} - seeded
        self.assertEqual(missing, set(), f"RoleName names no seeded Role: {missing}")

    def test_seeded_record_type_names_exist(self):
        """`RecordTypeName` claims to mirror rows migration records/0002 seeds."""
        from apps.records.models import RecordType

        seeded = set(RecordType.objects.values_list("name", flat=True))
        missing = {t.value for t in RecordTypeName} - seeded
        self.assertEqual(missing, set(), f"RecordTypeName names no seeded RecordType: {missing}")


def _format(offenders):
    return "\n".join(
        f"  {rel}:{line}  {value!r}"
        for rel, found in sorted(offenders.items())
        for line, value in found
    )
