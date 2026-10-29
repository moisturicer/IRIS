"""
`POST /records/import_excel/` with a real .xlsx, through the HTTP boundary (IR-315).

The importer needs `pyexcel`, which requirements/base.txt never declared -- only
its plugins were -- so every upload answered "pyexcel is not installed" in
production. The tests that should have shown it were skipped behind a
`find_spec("pyexcel")` guard and were later deleted with the fixed-stage suites
(IR-260). Nothing here is skipped: a missing dependency must fail the build.
"""
from io import BytesIO

import openpyxl
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from core.enums import PipelineStatus, RecordTypeName
from .models import Author, Record, RecordType
from .tests import make_user

#: The importer's documented columns (`parse_excel_import`), not the template's
#: output, so a drift between the two cannot hide here.
HEADERS = [
    "Title", "Abstract", "Year Accomplished", "Year Completed", "Record Type",
    "Classification", "PSCED Classification", "Is IP", "For Commercialization",
    "Community Extension", "Authors",
]
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def workbook(*rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(HEADERS)
    for row in rows:
        ws.append(row)
    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


class ExcelImportTests(APITestCase):
    def setUp(self):
        self.rdco = make_user("import_rdco@cit.edu", "RDCO")
        self.client.force_authenticate(self.rdco)

    def post(self, payload, name="legacy.xlsx"):
        return self.client.post(
            reverse("record-import-excel"),
            {"file": SimpleUploadedFile(name, payload, content_type=XLSX)},
            format="multipart",
        )

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
            ["First Imported Record"] + [None] * 10,
            [None, "An abstract with no title."] + [None] * 9,
            ["Third Imported Record"] + [None] * 10,
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
