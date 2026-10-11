"""Workflow audit event types, and a type column wide enough for them (IR-144)."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("audit", "0003_question_injection_event")]

    operations = [
        migrations.AlterField(
            model_name="auditevent",
            name="event_type",
            field=models.CharField(
                max_length=40,
                db_index=True,
                choices=[
                    ("LOGIN", "Login"),
                    ("LOGOUT", "Logout"),
                    ("FAILED_LOGIN", "Failed Login"),
                    ("ACCESS", "Record Access"),
                    ("UPLOAD", "File Upload"),
                    ("DOWNLOAD", "File Download"),
                    ("DELETE", "File Delete"),
                    ("RENAME", "File Rename"),
                    ("PIN_GENERATED", "PIN Generated"),
                    ("PIN_VERIFIED", "PIN Verified"),
                    ("ROLE_CHANGE", "Role Change"),
                    ("ACCOUNT_LOCKED", "Account Locked"),
                    ("ACCOUNT_UNLOCKED", "Account Unlocked"),
                    ("SESSION_REVOKE", "Session Revoked"),
                    ("QUESTION_INJECTION", "Reader Question Injection Flagged"),
                    ("SUBMITTED", "Submitted"),
                    ("ROUTED", "Routed"),
                    ("ASSIGNMENT_CLOSED", "Assignment Closed"),
                    ("DECISION_RECORDED", "Decision Recorded"),
                    ("PUBLISHED", "Published"),
                    ("RESUBMISSION_REQUESTED", "Revision Requested"),
                    ("REVISION_REQUEST_WITHDRAWN", "Revision Request Withdrawn"),
                    ("RESUBMITTED", "New Version Submitted"),
                    ("CLEARANCE_PRESERVED", "Clearance Preserved"),
                    ("SEAT_CLAIMED", "Seat Claimed"),
                    ("SEAT_ASSIGNED", "Seat Assigned"),
                    ("SEAT_NOMINATED", "Seat Nominated"),
                    ("SEAT_REASSIGNED", "Seat Reassigned"),
                    ("SEAT_WITHDRAWN", "Seat Withdrawn"),
                    ("REVIEWER_ADDED", "Reviewer Added"),
                    ("SEAT_OPENED", "Seat Opened"),
                    ("RECORD_WITHDRAWN", "Record Withdrawn"),
                    ("DOCUMENT_REQUESTED", "Documents Requested"),
                    ("DOCUMENT_REQUEST_FULFILLED", "Document Request Fulfilled"),
                    ("DOCUMENT_REQUEST_ACCEPTED", "Requested Document Accepted"),
                    ("DOCUMENT_REQUEST_REJECTED", "Requested Document Rejected"),
                    ("DOCUMENT_REQUEST_WITHDRAWN", "Document Request Withdrawn"),
                ],
            ),
        ),
    ]
