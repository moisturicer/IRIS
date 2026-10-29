"""
`POST /records/import_excel/` with a real .xlsx, through the HTTP boundary (IR-315).

The importer needs `pyexcel`, which requirements/base.txt never declared -- only
its plugins were -- so every upload answered "pyexcel is not installed" in
production. The tests that should have shown it were skipped behind a
`find_spec("pyexcel")` guard and were later deleted with the fixed-stage suites
(IR-260). Nothing here is skipped: a missing dependency must fail the build.
"""
from io import BytesIO
from unittest.mock import patch

import openpyxl
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core.enums import PipelineStatus, RecordTypeName
from .models import Author, Record, RecordOwner, RecordType
from .tests import make_user

#: The importer's documented columns (`parse_excel_import`), not the template's
#: output, so a drift between the two cannot hide here.
HEADERS = [
    "Title", "Abstract", "Year Accomplished", "Year Completed", "Record Type",
    "Classification", "PSCED Classification", "Is IP", "For Commercialization",
    "Community Extension", "Authors",
]
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def row(*cells):
    """The leading cells of one data row, blank to the last column."""
    return [*cells] + [None] * (len(HEADERS) - len(cells))


def workbook(*rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(HEADERS)
    for row in rows:
        ws.append(row)
    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


class ImportTestCase(APITestCase):
    """Signed in as RDCO, uploading through the real endpoint."""

    def setUp(self):
        self.rdco = make_user("import_rdco@cit.edu", "RDCO")
        self.client.force_authenticate(self.rdco)

    def post(self, payload, name="legacy.xlsx"):
        return self.client.post(
            reverse("record-import-excel"),
            {"file": SimpleUploadedFile(name, payload, content_type=XLSX)},
            format="multipart",
        )

    def post_rows(self, *rows):
        return self.post(workbook(*rows))


class ExcelImportTests(ImportTestCase):
    def test_a_real_xlsx_upload_creates_a_published_record(self):
        response = self.post(workbook([
            "An Imported Legacy Record", "A legacy abstract.", 2021, 2022,
            RecordTypeName.PROJECT, None, None, "YES", "no", "TRUE",
            "Juan Dela Cruz, Maria Santos",
        ]))

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["created"], 1, response.data["log"])
        self.assertEqual(response.data["skipped"], 0, response.data["log"])

        record = Record.objects.get(title="An Imported Legacy Record")
        self.assertEqual(record.pipeline_status, PipelineStatus.PUBLISHED)
        self.assertEqual(record.record_type, RecordType.objects.get(name=RecordTypeName.PROJECT))
        self.assertEqual((record.year_accomplished, record.year_completed), (2021, 2022))
        self.assertEqual(
            (record.is_ip, record.for_commercialization, record.community_extension),
            (True, False, True),
        )
        self.assertTrue(record.owners.filter(user=self.rdco, is_primary=True).exists())
        self.assertEqual(
            sorted(Author.objects.filter(record=record).values_list("name", flat=True)),
            ["Juan Dela Cruz", "Maria Santos"],
        )

    def test_a_row_without_a_title_is_reported_by_row_and_the_rest_still_import(self):
        """
        Rows are independent: one bad row is named in the log by its sheet row
        number and skipped, and the rows around it are still created.
        """
        response = self.post(workbook(
            row("First Imported Record"),
            row(None, "An abstract with no title."),
            row("Third Imported Record"),
        ))

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual((response.data["created"], response.data["skipped"]), (2, 1))
        self.assertIn("Row 3: skipped — Title is required.", response.data["log"])
        self.assertEqual(
            set(Record.objects.filter(added_by=self.rdco).values_list("title", flat=True)),
            {"First Imported Record", "Third Imported Record"},
        )

    def test_a_file_that_is_not_a_spreadsheet_is_reported_and_creates_nothing(self):
        response = self.post(b"this is not a workbook", name="notes.xlsx")

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual((response.data["created"], response.data["skipped"]), (0, 1))
        self.assertIn("Could not open file", response.data["log"])
        self.assertFalse(Record.objects.filter(added_by=self.rdco).exists())


class ImportRowIsAllOrNothingTests(ImportTestCase):
    """
    A row is a Record, its primary owner and its authors, saved together or
    not at all (IR-637). The import publishes straight away, so a half-saved
    row was a public, unreviewed record the log said was never created.
    """

    def test_a_failed_author_write_leaves_nothing_of_its_row_and_spares_the_others(self):
        real_create = Author.objects.create

        def failing_for_one_row(**fields):
            if fields["name"] == "Broken Author":
                raise IntegrityError("author write refused")
            return real_create(**fields)

        payload = workbook(
            row("Row Before", None, None, None, None, None, None, None, None, None, "Ana Reyes"),
            row("The Failing Row", None, None, None, None, None, None, None, None, None,
                "Good Author, Broken Author"),
            row("Row After", None, None, None, None, None, None, None, None, None, "Ben Cruz"),
        )
        with patch.object(Author.objects, "create", side_effect=failing_for_one_row):
            response = self.post(payload)

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual((response.data["created"], response.data["skipped"]), (2, 1), response.data["log"])
        # Nothing of the failing row: no Record, so no owner and no author either.
        self.assertFalse(Record.objects.filter(title="The Failing Row").exists())
        self.assertFalse(Author.objects.filter(name__in=["Good Author", "Broken Author"]).exists())
        self.assertEqual(RecordOwner.objects.filter(user=self.rdco).count(), 2)
        self.assertIn("✗  Row 3: not saved — The Failing Row — author write refused", response.data["log"])
        self.assertEqual(
            set(Record.objects.filter(added_by=self.rdco).values_list("title", flat=True)),
            {"Row Before", "Row After"},
        )
        self.assertEqual(
            set(Author.objects.values_list("name", flat=True)), {"Ana Reyes", "Ben Cruz"},
        )

    def test_a_real_database_error_mid_row_is_rolled_back_and_the_import_continues(self):
        """
        No mock: Postgres refuses an author name longer than its column, which
        aborts the transaction. The row's savepoint is what lets the rows
        after it still be written.
        """
        too_long = "A" * 201

        response = self.post_rows(
            row("Before The Real Error"),
            row("Real Error Row", None, None, None, None, None, None, None, None, None, f"Fine Name, {too_long}"),
            row("After The Real Error"),
        )

        self.assertEqual((response.data["created"], response.data["skipped"]), (2, 1), response.data["log"])
        self.assertFalse(Record.objects.filter(title="Real Error Row").exists())
        self.assertFalse(Author.objects.filter(name="Fine Name").exists())
        line = next(l for l in response.data["log"].splitlines() if "Row 3:" in l)
        self.assertTrue(line.startswith("✗  Row 3: not saved — Real Error Row — "), line)
        self.assertEqual(
            set(Record.objects.filter(added_by=self.rdco).values_list("title", flat=True)),
            {"Before The Real Error", "After The Real Error"},
        )

    def test_a_failed_owner_write_leaves_no_published_record(self):
        with patch.object(RecordOwner.objects, "create", side_effect=IntegrityError("owner write refused")):
            response = self.post(workbook(row("Ownerless Record")))

        self.assertEqual((response.data["created"], response.data["skipped"]), (0, 1), response.data["log"])
        self.assertFalse(Record.objects.filter(title="Ownerless Record").exists())
        self.assertIn("✗  Row 2: not saved — Ownerless Record — owner write refused", response.data["log"])
