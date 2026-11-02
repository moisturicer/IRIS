"""One research-read policy in PostgreSQL, under row-level security (IR-718, ADR-049 §5, §7).

Additive: RLS is ENABLEd, not FORCEd, so the table owner the application
connects as today reads exactly as before. Only non-owner roles, the
restricted runtime roles of IR-717, are filtered. Policies are SELECT-only,
so those roles can never write. FORCE is a cutover step
(`provision_research_roles --force-row-security`).

The principal comes only from `iris_authz.current_research_claims()`, and
only the `record_read` and `reader_run` purposes read: an `ingestion` grant
reads nothing until IR-737 verifies the committed work item.
"""

from django.db import migrations

#: Mirrors `Record.objects.visible_to`; pinned by test_research_read_policy_db.
OFFICE_ROLES = ("IERC", "ITSO", "KTTO", "RDCO")
PUBLIC_STATUSES = ("published",)

ID_SET = "CAST((SELECT iris_authz.research_record_ids()) AS bigint[])"
VERIFIER_OR = "CASE WHEN current_user = 'iris_authz_verifier' THEN true ELSE {} END"

#: table -> the policy's USING expression.
POLICIES = {
    # The verifier reads these two inside research_record_ids(); CASE keeps
    # it from recursing into the policy that calls it.
    "records_record": VERIFIER_OR.format(f"id = ANY({ID_SET})"),
    "records_recordowner": VERIFIER_OR.format(f"record_id = ANY({ID_SET})"),
    "records_author": f"record_id = ANY({ID_SET})",
    "records_recordversion": f"record_id = ANY({ID_SET})",
    "documents_pdfextraction": f"record_id = ANY({ID_SET})",
    "ai_chunkset": f"record_id = ANY({ID_SET})",
    "ai_documentchunk": f"record_id = ANY({ID_SET})",
    "ai_chunkembedding": "chunk_id IN (SELECT id FROM public.ai_documentchunk)",
    "ai_recordembedding": f"record_id = ANY({ID_SET})",
    "ai_recordoverview": f"record_id = ANY({ID_SET})",
    "ai_paperbrief": f"record_id = ANY({ID_SET})",
}
PROTECTED_TABLES = tuple(POLICIES)

_offices = ", ".join(f"'{name}'" for name in OFFICE_ROLES)
_statuses = ", ".join(f"'{name}'" for name in PUBLIC_STATUSES)

FUNCTION = rf"""
CREATE FUNCTION iris_authz.research_record_ids() RETURNS bigint[]
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
    claims jsonb := iris_authz.current_research_claims();
    reader bigint;
    scope bigint;
    office boolean;
    found_ids bigint[];
BEGIN
    IF claims IS NULL OR claims->>'pur' IS NULL
       OR claims->>'pur' NOT IN ('record_read', 'reader_run') THEN
        RETURN '{{}}';
    END IF;
    reader := (claims->>'sub')::bigint;
    IF reader IS NULL THEN RETURN '{{}}'; END IF;
    IF claims->>'pur' = 'reader_run' THEN scope := (claims->>'rec')::bigint; END IF;
    SELECT coalesce(ro.name IN ({_offices}), false) INTO office
      FROM public.accounts_user u LEFT JOIN public.accounts_role ro ON ro.id = u.role_id
     WHERE u.id = reader;
    SELECT coalesce(array_agg(r.id), '{{}}') INTO found_ids
      FROM public.records_record r
     WHERE NOT r.is_deleted
       AND (scope IS NULL OR r.id = scope)
       AND (coalesce(office, false)
            OR r.pipeline_status IN ({_statuses})
            OR r.adviser_id = reader
            OR EXISTS (SELECT 1 FROM public.records_recordowner o
                        WHERE o.record_id = r.id AND o.user_id = reader));
    RETURN found_ids;
END
$$;
REVOKE ALL ON FUNCTION iris_authz.research_record_ids() FROM PUBLIC;
"""


#: A runtime login must never own or migrate research tables.
REFUSE_RUNTIME_LOGIN = r"""
DO $$
DECLARE
    role_name text;
BEGIN
    FOREACH role_name IN ARRAY ARRAY['iris_ai_runtime', 'iris_django_runtime'] LOOP
        -- Superusers count as members of every role; they are maintenance.
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = role_name)
           AND NOT (SELECT rolsuper FROM pg_roles WHERE rolname = current_user)
           AND pg_has_role(current_user, role_name, 'MEMBER') THEN
            RAISE EXCEPTION 'migrations must not run as a research runtime login (%)', role_name
                USING ERRCODE = 'insufficient_privilege';
        END IF;
    END LOOP;
END
$$;
"""


def forward_sql() -> str:
    parts = [REFUSE_RUNTIME_LOGIN, FUNCTION]
    for table, using in POLICIES.items():
        parts.append(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY;")
        parts.append(
            f"CREATE POLICY iris_research_read ON public.{table} FOR SELECT USING ({using});"
        )
    return "\n".join(parts)


def reverse_sql() -> str:
    parts = []
    for table in POLICIES:
        parts.append(f"DROP POLICY IF EXISTS iris_research_read ON public.{table};")
        parts.append(f"ALTER TABLE public.{table} NO FORCE ROW LEVEL SECURITY;")
        parts.append(f"ALTER TABLE public.{table} DISABLE ROW LEVEL SECURITY;")
    parts.append("DROP FUNCTION IF EXISTS iris_authz.research_record_ids();")
    return "\n".join(parts)


class Migration(migrations.Migration):

    dependencies = [
        ("ai", "0034_research_grant_verifier"),
        ("records", "0022_download_grant"),
        ("documents", "0012_alter_documentrequest_party_alter_recordfile_party"),
    ]

    operations = [migrations.RunSQL(forward_sql(), reverse_sql())]
