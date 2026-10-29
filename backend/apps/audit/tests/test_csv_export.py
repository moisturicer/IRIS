import csv
import io
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from rest_framework.test import APITestCase

from apps.audit.models import AuditEvent
from apps.audit.tests.test_immutability import make_user
from core.enums import RoleName


EXPORT = "/api/v1/audit/export/"
COLUMNS = "created_at,event_type,actor_id,actor_role,record_id,party,from_party,to_party,outcome,version,policy,preserved_parties,reset_parties,request_id,item_ids,reason,metadata_json".split(",")


class AuditCsvTests(APITestCase):
    def setUp(self):
        self.rdco = make_user("csv@cit.edu", RoleName.RDCO)
        self.client.force_authenticate(self.rdco)

    def read_csv(self, params=None):
        response = self.client.get(EXPORT, params or {})
        self.assertEqual(response.status_code, 200)
        content = b"".join(response.streaming_content) if response.streaming else response.content
        reader = csv.DictReader(io.StringIO(content.decode()))
        self.assertEqual(reader.fieldnames, COLUMNS)
        return list(reader)

    def test_exports_every_matching_row_and_workflow_metrics_without_pagination(self):
        start = datetime(2026, 10, 1, 8, tzinfo=timezone.utc)
        for hours, (kind, meta) in enumerate([
            ("SUBMITTED", {"to_party": "adviser", "version": 1}),
            ("CLEARANCE_PRESERVED", {"party": "itso", "policy": "clearance_aware", "version": 2}),
            ("DECISION_RECORDED", {"party": "adviser", "final": True, "outcome": "publish", "version": 2}),
        ]):
            with patch("django.utils.timezone.now", return_value=start + timedelta(hours=hours)):
                AuditEvent.objects.create(event_type=kind, user=self.rdco, metadata=meta)
        rows = self.read_csv({"page_size": 1, "page": 2})
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["event_type"], "SUBMITTED")
        elapsed = datetime.fromisoformat(rows[-1]["created_at"]) - datetime.fromisoformat(rows[0]["created_at"])
        self.assertEqual(elapsed.total_seconds(), 7200)
        self.assertTrue(json.loads(rows[-1]["metadata_json"])["final"])
        self.assertEqual(sum(r["event_type"] == "CLEARANCE_PRESERVED" for r in rows), 1)
        self.assertEqual(rows[0]["actor_id"], str(self.rdco.pk))
        self.assertEqual(rows[0]["actor_role"], RoleName.RDCO)

    def test_date_record_actor_and_type_filters_match_the_screen(self):
        from apps.records.models import Record
        record = Record.objects.create(title="Exported record")
        other = Record.objects.create(title="Other record")
        with patch("django.utils.timezone.now", return_value=datetime(2026, 10, 2, 12, tzinfo=timezone.utc)):
            for _ in range(25):
                AuditEvent.objects.create(event_type="ROUTED", user=self.rdco, record=record, metadata={"from_party": "adviser", "to_party": "itso"})
            AuditEvent.objects.create(event_type="LOGIN", user=self.rdco, record=record)
            AuditEvent.objects.create(event_type="ROUTED", user=self.rdco, record=other)
        with patch("django.utils.timezone.now", return_value=datetime(2026, 10, 1, 12, tzinfo=timezone.utc)):
            AuditEvent.objects.create(event_type="ROUTED", user=self.rdco, record=record)
        params = {"record": record.pk, "user": self.rdco.pk, "event_type": "ROUTED", "from": "2026-10-02", "to": "2026-10-02"}
        rows = self.read_csv(params)
        self.assertEqual(len(rows), 25)
        self.assertEqual({r["record_id"] for r in rows}, {str(record.pk)})
        listed = self.client.get("/api/v1/audit/", params)
        self.assertEqual(listed.data["count"], 25)

    def test_non_rdco_roles_cannot_export_even_with_django_staff_flag(self):
        for role in [RoleName.STUDENT, RoleName.ADVISER, RoleName.ITSO, RoleName.IERC, RoleName.KTTO, None]:
            with self.subTest(role=role):
                actor = make_user(f"{role or 'none'}@cit.edu", role)
                actor.is_staff = True
                actor.save()
                self.client.force_authenticate(actor)
                self.assertEqual(self.client.get(EXPORT).status_code, 403)

    def test_csv_escaping_lists_and_formula_protection_preserve_metadata(self):
        reason = '=HYPERLINK("example")\nNeeds, revision'
        meta = {"request": 9, "items": [{"id": 4, "label": "Consent, signed"}], "reason": reason}
        AuditEvent.objects.create(event_type="DOCUMENT_REQUEST_REJECTED", metadata=meta)
        row = self.read_csv()[0]
        self.assertEqual(row["reason"], "'" + reason)
        self.assertEqual(json.loads(row["metadata_json"]), meta)
        self.assertEqual(row["request_id"], "9")
        self.assertEqual(json.loads(row["item_ids"]), [4])

    def test_empty_export_has_headers_and_invalid_filters_are_bad_requests(self):
        self.assertEqual(self.read_csv(), [])
        for params in [{"from": "bad"}, {"record": "bad"}, {"from": "2026-10-03", "to": "2026-10-01"}]:
            for url in [EXPORT, "/api/v1/audit/"]:
                self.assertEqual(self.client.get(url, params).status_code, 400)

    def test_export_route_does_not_allow_mutating_history(self):
        for method in [self.client.post, self.client.put, self.client.patch, self.client.delete]:
            self.assertEqual(method(EXPORT).status_code, 405)

    def test_deleted_subjects_keep_their_ids_in_csv_and_screen(self):
        from apps.records.models import Record
        record = Record.objects.create(title="Deleted subject")
        actor = make_user("deleted@cit.edu", RoleName.ADVISER)
        actor_id, record_id = actor.pk, record.pk
        AuditEvent.objects.create(event_type="SUBMITTED", user=actor, record=record)
        actor.delete()
        record.delete()
        row = self.read_csv()[0]
        self.assertEqual(row["actor_id"], str(actor_id))
        self.assertEqual(row["record_id"], str(record_id))
        listed = self.client.get("/api/v1/audit/").data["results"][0]
        self.assertEqual(listed["user"], actor_id)
        self.assertEqual(listed["record"], record_id)
