"""The space-keyed Record vectors join the research-read policy (IR-739, ADR-049 §5, §23).

``ai_recordspaceembedding`` was created by IR-752 and read by nothing. IR-739
moves the readers onto it, including the ``ai/`` runtime's
``research_record_vectors``, so it needs what every other protected relation
has: row-level security with the same SELECT policy as ``ai_recordembedding``
(a reader sees a vector only for a Record it may research), and, through
``PROTECTED_TABLES``, the runtime role's SELECT grant.

Same posture as ``0035``: RLS is ENABLEd, not FORCEd, so the owner the
application connects as reads exactly as before; only non-owner restricted roles
are filtered. FORCE stays a cutover step.
"""

from django.db import migrations

TABLE = "ai_recordspaceembedding"
USING = "record_id = ANY(CAST((SELECT iris_authz.research_record_ids()) AS bigint[]))"

FORWARD = f"""
ALTER TABLE public.{TABLE} ENABLE ROW LEVEL SECURITY;
CREATE POLICY iris_research_read ON public.{TABLE} FOR SELECT USING ({USING});
"""

REVERSE = f"""
DROP POLICY IF EXISTS iris_research_read ON public.{TABLE};
ALTER TABLE public.{TABLE} NO FORCE ROW LEVEL SECURITY;
ALTER TABLE public.{TABLE} DISABLE ROW LEVEL SECURITY;
"""


class Migration(migrations.Migration):

    dependencies = [
        ("ai", "0041_embedding_space_activation"),
    ]

    operations = [migrations.RunSQL(FORWARD, REVERSE)]
