"""
A person who has not answered the notice is refused on **every** route (ADR-054 decision 3, IR-789).

`apps/accounts/test_notice.py` proves the block on a handful of URLs. This
proves the claim the ticket makes, "every other API call answers with a
distinct `notice_acceptance_required` code": it fires **every declared case of
every route** in the authorization matrix (`access/table.py`), with a real
token, as a student who has not answered, and fails on any route that answers
anything else.

The matrix itself cannot show this. Its runner signs in with
`force_authenticate`, which skips the authentication class where the block
lives. Here the request carries a real bearer token instead, so the same
authentication path the browser takes runs.

Exempt by design, and listed so that a new exemption is a visible decision:

- the routes `notice.ALLOWED_WHILE_UNANSWERED` names (read the notice, answer it,
  sign out), and
- routes whose view has **no authentication class at all** -- token refresh and
  the two password-recovery routes. They never look at a token, so there is no
  signed-in person for the block to stop.

Sign-in, registration and email activation are *not* exempt: they do run the
authentication class, so a request that carries an unanswered person's token is
refused there too, as "every other API call" says. A client that wants to sign
in as someone else signs out first, which is allowed.
"""

import dataclasses
import json
import shutil
import tempfile

import pytest
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.accounts import notice
from apps.accounts.sessions import start_session
from apps.accounts.tests import make_unanswered
from apps.tests.access.routes import enumerate_routes, view_class
from apps.tests.access.runner import _send
from apps.tests.access.table import DECLARED, Shadowed
from apps.tests.access.world import build_world

#: Views that authenticate nobody, so the block has no one to stop.
NO_AUTHENTICATION = frozenset({
    ("accounts", "token-refresh"),
    ("accounts", "password-reset-request"),
    ("accounts", "password-reset-confirm"),
})


@pytest.mark.db_required
class UnansweredNoticeBlocksEveryRouteTests(APITestCase):
    @classmethod
    def setUpClass(cls):
        cls._media_root = tempfile.mkdtemp(prefix="iris-notice-block-")
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
        cls.person = make_unanswered(cls.world.users["other"])
        cls.token = str(start_session(cls.person).access_token)

    def fire(self, route, method, case):
        call = dataclasses.replace(
            case.call, headers={**case.call.headers, "HTTP_AUTHORIZATION": f"Bearer {self.token}"},
        )
        # user=None: no `force_authenticate`, so the real authentication class runs.
        return _send(self.client, route, method, call, self.world, None, None)

    def declared_cases(self):
        routes = {route.key: route for route in enumerate_routes()}
        for app, table in DECLARED.items():
            for name, entry in table.items():
                if isinstance(entry, Shadowed):
                    continue
                for method in sorted(entry.methods):
                    for case in entry.cases(method):
                        yield app, name, routes[(app, name)], method, case

    def test_every_route_but_the_exempt_ones_answers_notice_acceptance_required(self):
        from apps.ai.composition import use_composition_root
        from apps.ai.models import VECTOR_COLUMN_DIMENSIONS
        from apps.ai.providers.fakes import DeterministicEmbeddingProvider
        from apps.ai.tests.corpus import root_with

        failures, fired, exempt = [], 0, set()
        with override_settings(AI_DURABLE_ASK=False, AI_RESEARCH_LANE="off", AI_RUNTIME_READER=True):
            with use_composition_root(root_with(
                embedder=DeterministicEmbeddingProvider(dimensions=VECTOR_COLUMN_DIMENSIONS),
            )):
                for app, name, route, method, case in self.declared_cases():
                    if name in notice.ALLOWED_WHILE_UNANSWERED:
                        exempt.add((app, name))
                        continue
                    if (app, name) in NO_AUTHENTICATION:
                        # Named, not inferred: it must still really have no authenticators.
                        self.assertEqual(
                            list(getattr(view_class(route.view), "authentication_classes", None) or []),
                            [], f"{app}:{name} is listed as unauthenticated but authenticates",
                        )
                        exempt.add((app, name))
                        continue
                    response = self.fire(route, method, case)
                    fired += 1
                    try:
                        code = json.loads(response.body).get("code")
                    except (ValueError, AttributeError):
                        code = None
                    if response.status != 403 or code != notice.ACCEPTANCE_REQUIRED_CODE:
                        failures.append(
                            f"{method} {app}:{name}: {response.status} {response.body[:120]!r}"
                        )
        self.assertEqual(failures, [], f"\n{len(failures)} route(s) let an unanswered person through:\n"
                         + "\n".join(failures))
        # A sweep that fires nothing proves nothing.
        self.assertGreater(fired, 100)
        self.assertEqual(
            exempt,
            {("accounts", n) for n in notice.ALLOWED_WHILE_UNANSWERED if n.startswith(("notice-", "auth-"))}
            | NO_AUTHENTICATION,
        )

    def test_the_person_answering_is_let_through_on_the_same_token(self):
        """The same token, the same sweep's route set, passes once the notice is answered."""
        from apps.accounts.models import DataNotice

        notice.answer_notice(self.person, notice_version=DataNotice.current().number, ai_consent=False)
        route = next(r for r in enumerate_routes() if r.key == ("accounts", "user-me"))
        _, _, _, method, case = next(
            c for c in self.declared_cases() if c[:2] == ("accounts", "user-me") and c[3] == "GET"
        )
        self.assertEqual(self.fire(route, method, case).status, 200)
