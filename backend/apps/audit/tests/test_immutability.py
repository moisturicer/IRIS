"""
Audit rows are insert-only, enforced by the database (IR-166, NFR-S5).

Immutability used to rest on the absence of an endpoint, so anything else with
database access -- a shell, a careless migration, a future view -- could
rewrite history. The guard is a PostgreSQL trigger (migration 0005), so these
tests go through the ORM *and* raw SQL: an application-level check would pass
the first and fail the second.

No UPDATE that changes anything is permitted, so the foreign keys are
`DO_NOTHING` without a constraint: deleting a User or a Record leaves its
audit rows exactly as they were, still carrying its id.
"""

from django.db import DatabaseError, connection, transaction
from django.test import TestCase
from rest_framework.test import APITestCase

from apps.accounts.models import Role, User
from apps.audit.models import AuditEvent
from apps.audit.services import create_audit_event
from core.enums import RoleName

AUDIT = "/api/v1/audit/"


def make_user(email, role_name=None):
    role = Role.objects.get_or_create(name=role_name)[0] if role_name else None
    return User.objects.create_user(
        email=email, password="pw12345!", first_name="Audit", last_name="Test",
        role=role, is_verified=True,
    )


class AuditRowsAreInsertOnlyTests(TestCase):
    def setUp(self):
        self.user = make_user("audited@cit.edu")
        create_audit_event(AuditEvent.LOGIN, self.user, metadata={"email": "audited@cit.edu"})
        self.event = AuditEvent.objects.get(user=self.user)

    def refused(self, action):
        # Each attempt in its own savepoint, so the test transaction survives it.
        with self.assertRaises(DatabaseError), transaction.atomic():
            action()

    def test_the_application_can_still_insert(self):
        create_audit_event(AuditEvent.LOGOUT, self.user, metadata={"email": "audited@cit.edu"})
        self.assertEqual(AuditEvent.objects.filter(user=self.user).count(), 2)

    def test_saving_a_changed_row_is_refused(self):
        self.event.metadata = {"email": "someone-else@cit.edu"}
        self.refused(self.event.save)

    def test_a_queryset_update_is_refused(self):
        self.refused(lambda: AuditEvent.objects.filter(pk=self.event.pk).update(event_type=AuditEvent.LOGOUT))

    def test_raw_sql_update_is_refused(self):
        def update():
            with connection.cursor() as cursor:
                cursor.execute("UPDATE audit_auditevent SET created_at = now() WHERE id = %s", [self.event.pk])
        self.refused(update)

    def test_deleting_a_row_is_refused(self):
        self.refused(self.event.delete)

    def test_a_queryset_delete_is_refused(self):
        self.refused(lambda: AuditEvent.objects.all().delete())

    def test_raw_sql_delete_is_refused(self):
        def delete():
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM audit_auditevent")
        self.refused(delete)

    def test_nothing_changed_after_the_refusals(self):
        self.refused(lambda: AuditEvent.objects.filter(pk=self.event.pk).update(metadata={}))
        self.refused(self.event.delete)
        fresh = AuditEvent.objects.get(pk=self.event.pk)
        self.assertEqual(fresh.metadata, {"email": "audited@cit.edu"})
        self.assertEqual(fresh.created_at, self.event.created_at)

    def test_deleting_the_user_leaves_the_row_exactly_as_it_was(self):
        # DO_NOTHING with no constraint: the row keeps the deleted account's id.
        user_id = self.user.pk
        self.user.delete()
        fresh = AuditEvent.objects.get(pk=self.event.pk)
        self.assertEqual(fresh.user_id, user_id)
        self.assertEqual(fresh.metadata, {"email": "audited@cit.edu"})

    def test_clearing_who_acted_is_refused(self):
        # The hole SET_NULL needed: no UPDATE may strip attribution.
        self.refused(lambda: AuditEvent.objects.filter(pk=self.event.pk).update(user=None))

    def test_an_unchanged_save_is_not_a_change(self):
        self.event.save()
        self.assertEqual(AuditEvent.objects.get(pk=self.event.pk).metadata, {"email": "audited@cit.edu"})

    def test_repointing_a_row_at_another_user_is_refused(self):
        other = make_user("other@cit.edu")
        self.refused(lambda: AuditEvent.objects.filter(pk=self.event.pk).update(user=other))


class NoRouteMutatesTheAuditLogTests(APITestCase):
    """The audit API is read-only even for RDCO, its only reader."""

    def setUp(self):
        self.client.force_authenticate(make_user("rdco@cit.edu", RoleName.RDCO))

    def test_the_list_is_readable(self):
        self.assertEqual(self.client.get(AUDIT).status_code, 200)

    def test_a_row_whose_user_was_deleted_still_lists(self):
        gone = make_user("gone@cit.edu")
        create_audit_event(AuditEvent.LOGIN, gone, metadata={"email": "gone@cit.edu"})
        gone_id = gone.pk
        gone.delete()
        response = self.client.get(AUDIT, {"page_size": 100})
        self.assertEqual(response.status_code, 200)
        [row] = [r for r in response.data["results"] if r["metadata"] == {"email": "gone@cit.edu"}]
        self.assertEqual(row["user"], gone_id)
        self.assertIsNone(row["user_name"])

    def test_every_write_method_is_not_allowed(self):
        for method in ("post", "put", "patch", "delete"):
            with self.subTest(method=method):
                response = getattr(self.client, method)(AUDIT, {}, format="json")
                self.assertEqual(response.status_code, 405)

    def test_options_advertises_no_write_method(self):
        allow = self.client.options(AUDIT)["Allow"]
        for method in ("POST", "PUT", "PATCH", "DELETE"):
            self.assertNotIn(method, allow)

    def test_no_url_under_the_audit_prefix_addresses_a_single_event(self):
        # Exercise the boundary: a read-only CSV collection is allowed, but
        # a detail route must not expose a row for updates or deletion.
        event = AuditEvent.objects.create(event_type=AuditEvent.LOGIN)
        for method in ("get", "put", "patch", "delete"):
            with self.subTest(method=method):
                response = getattr(self.client, method)(f"{AUDIT}{event.pk}/")
                self.assertEqual(response.status_code, 404)
