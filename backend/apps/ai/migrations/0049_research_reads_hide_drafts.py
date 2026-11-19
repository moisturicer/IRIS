"""An unsubmitted draft is its creator's alone in the research reads too (IR-1227, ADR-009 decision 6).

`iris_authz.research_record_ids()` mirrors `Record.objects.visible_to`. That
predicate now gives a draft to the account that created it (`added_by`) and
nobody else, a co-owner included, and holds every other ground -- ownership,
office staff, the named Adviser, the public catalogue -- only for a submitted
record, so this swaps the same condition into the function. It reads
`added_by_id`, which `provision_research_roles` grants the verifier.

Built from 0037's SQL, as 0037 was built from 0035's, so only this clause
differs; CREATE OR REPLACE keeps the function's owner and grants. It only narrows: nobody reads a record they
could not read before; a draft's creator, and every reader of a submitted
record, reads exactly as before.
`test_research_reads` pins the two predicates to the same population.
"""

from importlib import import_module

from django.db import migrations

_previous = import_module("apps.ai.migrations.0037_reader_session_reads")
_statuses = import_module("apps.ai.migrations.0035_research_read_policy")._statuses

DRAFT = "draft"

READABLE = """\
       AND (coalesce(office, false)
            OR r.pipeline_status IN ({statuses})
            OR r.adviser_id = reader
            OR EXISTS (SELECT 1 FROM public.records_recordowner o
                        WHERE o.record_id = r.id AND o.user_id = reader));"""

#: A draft is its creator's alone; every other ground holds only once submitted.
CREATOR_ALONE_READS_A_DRAFT = """\
       AND ((r.pipeline_status = '{draft}' AND r.added_by_id = reader)
            OR (r.pipeline_status <> '{draft}'
                AND (coalesce(office, false)
                     OR r.pipeline_status IN ({statuses})
                     OR r.adviser_id = reader
                     OR EXISTS (SELECT 1 FROM public.records_recordowner o
                                 WHERE o.record_id = r.id AND o.user_id = reader))));"""


def _swap(sql: str, old: str, new: str) -> str:
    if sql.count(old) != 1:
        raise RuntimeError(f"0049 expected one {old!r}")
    return sql.replace(old, new)


PREVIOUS_IDS = _previous.IDS
IDS = _swap(
    PREVIOUS_IDS,
    READABLE.format(statuses=_statuses),
    CREATOR_ALONE_READS_A_DRAFT.format(statuses=_statuses, draft=DRAFT),
)


class Migration(migrations.Migration):

    dependencies = [
        ("ai", "0048_chunk_keyword_text"),
    ]

    operations = [migrations.RunSQL(IDS, PREVIOUS_IDS)]
