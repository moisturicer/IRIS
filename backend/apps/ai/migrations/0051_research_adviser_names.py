"""The AI runtime may read a readable paper's Adviser by name (IR-1278, ADR-049 amendment 2026-11-23).

`paper_details` returns what the Publish form recorded. Every field is a
`records_record` or `records_author` column the runtime already reads under
the row policy, except the Adviser, who is an account: the runtime reads no
`accounts_user` row. This function answers for exactly the Records the caller's
grant may read (`research_record_ids()`, which applies the Paper Chat scope and
the IR-1252 disclosure gate), and returns a name and nothing else: never an
email, id or profile.

The name is the one the catalogue shows (`User.get_full_name()`), or the plain
text kept for a deleted Adviser (IR-785). SECURITY DEFINER, so
`provision_research_roles` hands it to `iris_authz_verifier`, gives that role
the name columns, and grants EXECUTE to `iris_ai_runtime` alone.
"""

from django.db import migrations

ADVISERS = r"""
CREATE FUNCTION iris_authz.research_advisers(p_records bigint[])
RETURNS TABLE (record_id bigint, name text)
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
    SELECT r.id,
           coalesce(nullif(concat_ws(' ', nullif(u.first_name, ''), nullif(u.middle_initial, ''),
                                     nullif(u.last_name, '')), ''),
                    nullif(btrim(r.adviser_name), ''))
      FROM public.records_record r
      LEFT JOIN public.accounts_user u ON u.id = r.adviser_id
     WHERE r.id = ANY(p_records)
       -- The verifier reads every Record; only those this grant may read are answered.
       AND r.id = ANY(iris_authz.research_record_ids())
$$;
REVOKE ALL ON FUNCTION iris_authz.research_advisers(bigint[]) FROM PUBLIC;
"""

#: What `provision_research_roles` would do, done here too, so a database provisioned before
#: this migration has a working `paper_details` without re-running it (as 0050 does).
#: Handing the function to the verifier needs a superuser; otherwise provisioning does it.
GRANTS = """DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'iris_authz_verifier') THEN
        GRANT SELECT (first_name, middle_initial, last_name) ON public.accounts_user TO iris_authz_verifier;
        GRANT SELECT (adviser_id, adviser_name) ON public.records_record TO iris_authz_verifier;
        IF (SELECT rolsuper FROM pg_roles WHERE rolname = current_user) THEN
            ALTER FUNCTION iris_authz.research_advisers(bigint[]) OWNER TO iris_authz_verifier;
        END IF;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'iris_ai_runtime') THEN
        GRANT EXECUTE ON FUNCTION iris_authz.research_advisers(bigint[]) TO iris_ai_runtime;
    END IF;
END $$"""

DROP = "DROP FUNCTION IF EXISTS iris_authz.research_advisers(bigint[]);"


class Migration(migrations.Migration):

    dependencies = [
        ("ai", "0050_runtime_reads_only_published"),
        ("accounts", "0024_session_remembered"),
        ("records", "0043_setup_requirements"),
    ]

    operations = [
        migrations.RunSQL(ADVISERS, DROP),
        # The column grants stay on reverse: earlier migrations never revoke the verifier's.
        migrations.RunSQL(GRANTS, migrations.RunSQL.noop),
    ]
