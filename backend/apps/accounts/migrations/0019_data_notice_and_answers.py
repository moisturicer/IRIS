"""
The data notice as numbered versions, and each person's answer (IR-789).

ADR-054 decisions 1-4 and 17. Creates `DataNotice`, `NoticeAnswer` and the
three columns on `User` that mirror a person's last answer, then **creates
version 1 from the text the frontend carried before** -- `DataNotice.tsx`
(the interim registration notice, IR-540) and `lib/dpaTerms.ts` (the RA 10173
terms, IR-123) -- so that IRIS never runs without a notice.

Existing accounts get `answered_notice_version = NULL`: unanswered, and they
answer at next sign-in (decision 17). Nothing here marks anyone as having
accepted version 1, including accounts whose legacy `consent_given` is true.

The text below is frozen on purpose. It is a copy, not an import: a later
edit to the frontend file must not change what a migration wrote. It is still
**pending the data protection officer's review** (IR-123); this migration moves
the existing words into the database and approves none of them.
"""

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models

V1_TITLE = "DPA Consent Registry (RA 10173)"
V1_SUBTITLE = "Cebu Institute of Technology - University Technology Transfer Office"

V1_SECTIONS = [
    {
        "title": "Interim notice",
        "body": (
            "Interim notice. The university's Terms of Service and Data Privacy Policy will "
            "replace it."
        ),
        "list": [
            "What IRIS keeps when you register: Your name, your CIT-U email, your college, your "
            "program or department, the role you ask for, and your password, which is stored "
            "only as a hash.",
            "Why: To create your account, to email you a verification link, and to send your "
            "role request to RDCO.",
            "Who sees your registration: RDCO staff, who approve or decline role requests, and "
            "IRIS's system administrators. If you are approved as an Adviser, anyone signed in "
            "to IRIS can see your name, email, college and department, so students can name "
            "you as their adviser.",
            "Research you submit later: Visible according to its review and publication state.",
        ],
    },
    {
        "title": "Notice review status",
        "body": (
            "This notice is pending CIT-U Data Protection Officer (DPO) / legal review before "
            "the pilot collects real consent."
        ),
    },
    {
        "title": "Republic Act No. 10173 (Data Privacy Act of 2012) Terms",
        "body": (
            "In compliance with the Data Privacy Act of 2012 (RA No. 10173), you consent to "
            "Cebu Institute of Technology - University collecting, storing and indexing the "
            "intellectual property disclosures, abstracts and manuscripts you submit, for the "
            "purposes described below."
        ),
    },
    {
        "title": "1. What we collect",
        "list": [
            "Account details: your name, your CIT-U email address, your assigned role, and your "
            "course, department or college as recorded by the university.",
            "Disclosure details: the title, abstract, keywords and classification of each "
            "submission, the adviser you nominate, the college of origin, and submission and "
            "review timestamps.",
            "Uploaded files: the manuscripts and supporting documents you upload, together with "
            "their file type and size.",
        ],
    },
    {
        "title": "2. How your submission is used",
        "list": [
            "Institutional search: submitted titles, abstracts and keywords are indexed so that "
            "CIT-U students and staff can find research across the university.",
            "Manuscript processing: IRIS extracts text from uploaded manuscripts and builds a "
            "search index to find relevant passages and support AI responses.",
            "Review workflow: your disclosure is routed to the offices you select or that your "
            "submission type requires, so they can record a clearance decision.",
            "Audit logging: security-relevant events such as sign-in, document access and "
            "document download are recorded so that access to your work can be accounted for.",
        ],
    },
    {
        "title": "3. External AI processing",
        "body": (
            "When AI features are enabled, IRIS sends data to external AI providers outside "
            "CIT-U to support search and AI responses. Personal or confidential information "
            "included in that text may also be sent."
        ),
        "list": [
            "Voyage AI receives manuscript text for embedding (building the search index), and "
            "search questions and candidate passages for reranking (ordering search results).",
            "The configured language-model providers receive questions, relevant conversation "
            "context and manuscript text to generate answers and summaries. A summary may use "
            "text from the whole manuscript. The providers used depend on the deployment "
            "configuration; contact the Research and Development Coordinating Office for the "
            "current provider details.",
            "Provider retention, processing locations and use of submitted data are subject to "
            "the configured providers' terms and account settings. These arrangements require "
            "institutional review; this notice does not promise that providers retain no data "
            "or that processing stays within CIT-U.",
        ],
    },
    {
        "title": "4. Your rights under RA 10173",
        "body": "Under RA 10173 you may:",
        "list": [
            "Access: view every disclosure recorded under your account at any time, from My "
            "Workspace.",
            "Correction: correct your own name and profile details from Settings, and ask the "
            "Research and Development Coordinating Office to correct any submission detail.",
            "Erasure: request deletion of a disclosure. The request is reviewed and, once "
            "approved, the record and its uploaded files are removed.",
            "Withdraw consent: contact the Research and Development Coordinating Office. "
            "Withdrawal cannot be completed from this system yet, and it does not undo review "
            "decisions already recorded.",
            "Complain: raise a concern with CIT-U's Data Protection Officer, and with the "
            "National Privacy Commission.",
        ],
    },
    {
        "title": "Consent Confirmation",
        "body": (
            "Ticking the consent box confirms that you have read these terms and agree to "
            "CIT-U processing your disclosure as described above."
        ),
    },
]


def create_version_one(apps, schema_editor):
    DataNotice = apps.get_model("accounts", "DataNotice")
    DataNotice.objects.get_or_create(
        number=1,
        defaults={"title": V1_TITLE, "subtitle": V1_SUBTITLE, "sections": V1_SECTIONS},
    )


class Migration(migrations.Migration):
    dependencies = [("accounts", "0018_seed_system_admin_role")]

    operations = [
        migrations.CreateModel(
            name="DataNotice",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("number", models.PositiveIntegerField(unique=True)),
                ("title", models.CharField(max_length=200)),
                ("subtitle", models.CharField(blank=True, max_length=300)),
                ("sections", models.JSONField()),
                ("published_at", models.DateTimeField(default=django.utils.timezone.now)),
                (
                    "published_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-number"]},
        ),
        migrations.CreateModel(
            name="NoticeAnswer",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("agreed_dpa", models.BooleanField()),
                ("ai_consent", models.BooleanField()),
                ("answered_at", models.DateTimeField(default=django.utils.timezone.now)),
                (
                    "notice",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="answers",
                        to="accounts.datanotice",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="notice_answers",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-answered_at", "-id"]},
        ),
        migrations.AddConstraint(
            model_name="noticeanswer",
            constraint=models.CheckConstraint(
                condition=models.Q(("agreed_dpa", True)), name="notice_answer_agreed_dpa"
            ),
        ),
        migrations.AddIndex(
            model_name="noticeanswer",
            index=models.Index(fields=["user", "-answered_at"], name="notice_answer_user_at_idx"),
        ),
        migrations.AddField(
            model_name="user",
            name="answered_notice_version",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="user",
            name="ai_consent",
            field=models.BooleanField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="user",
            name="notice_answered_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(create_version_one, migrations.RunPython.noop),
    ]
