"""
The endpoint authorization matrix: every route declared, every cell fired (IR-615).

CLAUDE.md says never add an endpoint without an object-level permission
check, and IR-153, IR-474, IR-476, IR-507 and IR-508 are each an endpoint that
shipped without one. Nothing enforced the rule. This module does, twice:

1. `RouteDeclarationTests` walks the URLconf and fails on **any route the
   table does not declare**, naming it. It needs no database, so it runs
   wherever the suite does.
2. `AccessMatrixTests` fires every declared case as every role and fails on
   any cell whose outcome differs, and on any refusal that tells a caller an
   object exists when they may not know it (`cells.judge`).

So the ticket's example -- someone adds `GET /documents/files/<id>/preview/`
and forgets the ownership check -- fails once as undeclared, and again once
declared, because "other user -> 404" gets 200.

The declared table is `access/table.py`. **A failing cell is a bug in the
route, not in the table** (IR-611): file it `area-security` and mark the cell
`KnownDefect`, never loosen the row.

Run:
    docker compose exec -T backend python -m pytest apps/tests/test_access_matrix.py -q
"""

import shutil
import tempfile

import pytest
from django.test import SimpleTestCase, override_settings
from django.urls import resolve
from rest_framework.test import APITestCase

from apps.tests.access.cells import (
    DENY, HIDE, OK, Case, KnownDefect, Observed, Response, judge,
)
from apps.tests.access.routes import enumerate_routes, name_collisions
from apps.tests.access.runner import observe
from apps.tests.access.table import DECLARED, PARTIAL, PENDING, TABLE, Entry, Shadowed
from apps.tests.access.world import ROLES, build_world


def undeclared(routes) -> list[str]:
    """Every route neither declared, pending nor out of scope, as a message."""
    problems = []
    for route in routes:
        if route.out_of_scope or route.app in PENDING:
            continue
        if route.name is None:
            problems.append(f"{route.pattern} has no URL name, so no table row can declare it")
        elif route.app not in TABLE:
            problems.append(
                f"{route} belongs to no declared or pending app: add the app to "
                "apps/tests/access/table.py"
            )
        elif route.name not in TABLE[route.app]:
            problems.append(
                f"{route} is not declared: add its row to apps/tests/access/table.py "
                "with one outcome per role"
            )
    return problems


def _routes_by_key():
    return {route.key: route for route in enumerate_routes()}


@pytest.mark.django_required
class RouteDeclarationTests(SimpleTestCase):
    """The table and the URLconf agree, route for route and method for method."""

    def test_every_route_is_declared(self):
        problems = undeclared(enumerate_routes())
        self.assertEqual(problems, [], "\n" + "\n".join(problems))

    def test_no_two_views_in_an_app_share_a_name(self):
        """The table is keyed by name; a shared one would leave a view untested."""
        self.assertEqual(name_collisions(enumerate_routes()), [])

    def test_every_declared_route_exists_with_exactly_its_methods(self):
        """A stale row, or a method added to a declared route, fails too."""
        routes = _routes_by_key()
        problems = []
        for app, entries in DECLARED.items():
            for name, entry in entries.items():
                route = routes.get((app, name))
                if route is None:
                    problems.append(f"{app}:{name} is declared but no such route exists")
                elif isinstance(entry, Entry) and set(entry.methods) != set(route.methods):
                    problems.append(
                        f"{route} answers {sorted(route.methods)}, "
                        f"the table declares {sorted(entry.methods)}"
                    )
        self.assertEqual(problems, [], "\n" + "\n".join(problems))

    def test_a_shadowed_route_really_is_unreachable(self):
        """`Shadowed` is a claim about the URLconf; check it rather than trust it."""
        routes = _routes_by_key()
        for app, entries in DECLARED.items():
            for name, entry in entries.items():
                if not isinstance(entry, Shadowed):
                    continue
                path = "/" + routes[(app, name)].pattern.replace("^", "").replace("$", "")
                with self.subTest(route=f"{app}:{name}"):
                    self.assertEqual(resolve(path).url_name, entry.by)

    def test_pending_apps_are_apps_with_routes(self):
        """A pending marker that hides nothing is one nobody remembers to delete."""
        apps_with_routes = {route.app for route in enumerate_routes()}
        self.assertEqual(set(PENDING) - apps_with_routes, set())
        self.assertEqual(set(PENDING) & set(TABLE), set(), "an app is either declared or pending")
        self.assertEqual(set(PARTIAL) - set(PENDING), set(), "partial coverage retains its pending marker")
        self.assertEqual(set(PARTIAL) & set(TABLE), set(), "complete apps have no partial declarations")

    def test_known_defects_cite_a_filed_issue(self):
        """A `KnownDefect` names a real ticket, never a placeholder."""
        for app, entries in DECLARED.items():
            for name, entry in entries.items():
                if not isinstance(entry, Entry):
                    continue
                for method in entry.methods:
                    for case in entry.cases(method):
                        for cell in case.cells:
                            if isinstance(cell, KnownDefect):
                                with self.subTest(route=f"{app}:{name}", method=method):
                                    self.assertRegex(cell.issue, r"^IR-\d+$")

    @override_settings(ROOT_URLCONF="apps.tests.access.dummy_urls")
    def test_an_undeclared_route_is_detected(self):
        """
        The ticket's example route, two `include()`s deep in a test URLconf,
        is found and named -- and nothing else in the real URLconf is.
        """
        problems = undeclared(enumerate_routes())
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("matrix-undeclared-preview", problems[0])
        self.assertIn("api/v1/documents/files/<int:pk>/preview/", problems[0])


@pytest.mark.db_required
class AccessMatrixTests(APITestCase):
    """
    Every declared case, as every role, against one world built once.

    One test per app, each collecting every failing cell before it fails, so
    a regression report lists all of them rather than whichever ran first.
    """

    @classmethod
    def setUpClass(cls):
        # Before super(): setUpTestData writes the fixtures' files.
        cls._media_root = tempfile.mkdtemp(prefix="iris-access-matrix-")
        cls._media_override = override_settings(MEDIA_ROOT=cls._media_root)
        cls._media_override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._media_override.disable()
        shutil.rmtree(cls._media_root, ignore_errors=True)

    @classmethod
    def setUpTestData(cls):
        cls.world = build_world()

    def run_app(self, app):
        routes = _routes_by_key()
        failures = []
        for name, entry in DECLARED[app].items():
            if isinstance(entry, Shadowed):
                continue
            route = routes[(app, name)]
            for method in sorted(entry.methods):
                for case in entry.cases(method):
                    failures.extend(self.run_case(route, method, case, entry.waiver))
        self.assertEqual(failures, [], f"\n{len(failures)} cell(s) failed:\n" + "\n".join(failures))

    def run_case(self, route, method, case: Case, waiver):
        failures = []
        label = f" [{case.label}]" if case.label else ""
        for role in ROLES:
            observed = observe(self.client, route, method, case.call, self.world, role, waiver)
            passed, reason = judge(case.cell(role), observed)
            if not passed:
                failures.append(f"{method} {route.name}{label} as {role}: {reason}")
        return failures

    def test_records_routes(self):
        self.run_app("records")

    def test_documents_routes(self):
        self.run_app("documents")

    def test_review_deadline_routes(self):
        self.run_app("reviews")

    def test_every_role_is_who_the_table_says(self):
        """The columns mean what `table.py` says, or every row means nothing."""
        from apps.reviews.models import ReviewerSeat

        users, record = self.world.users, self.world.objects["record"]
        seated = ReviewerSeat.objects.filter(assignment__record=record, state="in_review")
        self.assertEqual(
            {seat.reviewer for seat in seated if seat.assignment.party == "itso"},
            {users["seated"]},
        )
        self.assertEqual(record.pipeline_status, "in_review")
        self.assertTrue(record.owners.filter(user=users["owner"]).exists())
        self.assertEqual(record.adviser, users["adviser"])
        self.assertTrue(users["coordinator"].is_office_coordinator)
        self.assertFalse(
            ReviewerSeat.objects.filter(
                reviewer__in=[users["unseated"], users["coordinator"], users["rdco"]],
            ).exists()
        )
        self.assertIsNone(users["admin"].role)
        self.assertTrue(users["admin"].is_superuser)


@pytest.mark.django_required
class JudgeTests(SimpleTestCase):
    """The judge's own rules, on synthetic responses: no database needed."""

    def obs(self, status, body=b"x", missing=(), can_see=True, waiver=""):
        return Observed(Response(status, body), tuple(Response(*m) for m in missing), can_see, waiver)

    def test_a_404_that_differs_from_a_missing_id_is_a_leak(self):
        passed, reason = judge(HIDE, self.obs(404, b"Upload hidden", [(404, b"Not found")], False))
        self.assertFalse(passed)
        self.assertIn("confirms the object exists", reason)

    def test_a_403_to_someone_who_cannot_see_the_object_is_a_leak(self):
        """Even where the table says DENY: visibility decides, not the row."""
        passed, _ = judge(DENY, self.obs(403, b"Denied", [(404, b"Not found")], can_see=False))
        self.assertFalse(passed)

    def test_a_cited_waiver_allows_that_403(self):
        passed, _ = judge(
            DENY, self.obs(403, b"Denied", [(404, b"Not found")], can_see=False, waiver="ADR-022"),
        )
        self.assertTrue(passed)

    def test_a_role_gate_403_that_reads_like_a_missing_id_hides_nothing(self):
        passed, _ = judge(DENY, self.obs(403, b"Denied", [(403, b"Denied")], can_see=False))
        self.assertTrue(passed)

    def test_ok_refuses_every_refusal_and_fault(self):
        for status in (401, 403, 404, 405, 500):
            with self.subTest(status=status):
                self.assertFalse(judge(OK, self.obs(status))[0])
        self.assertTrue(judge(OK, self.obs(400))[0])

    def test_a_known_defect_fails_once_it_is_fixed(self):
        defect = KnownDefect(HIDE, "IR-1", "403")
        self.assertTrue(judge(defect, self.obs(403, b"Denied", [(404, b"Nope")], False))[0])
        passed, reason = judge(defect, self.obs(404, b"Nope", [(404, b"Nope")], False))
        self.assertFalse(passed)
        self.assertIn("remove its KnownDefect marker", reason)

