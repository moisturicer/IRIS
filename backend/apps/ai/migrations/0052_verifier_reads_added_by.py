"""The verifier may read every column `research_record_ids()` reads (IR-1285).

0049 (IR-1227) made the function read `records_record.added_by_id` and left the grant
to `provision_research_roles`, which `migrate` never runs. On a database migrated past
0049 without re-provisioning, the function raised `permission denied` and every Ask IRIS
question failed. Granted here, as 0050 and 0051 grant theirs. Skipped without the role.
"""

from django.db import migrations

GRANTS = """DO $$ BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'iris_authz_verifier') THEN
        GRANT SELECT (id, is_deleted, pipeline_status, is_embargoed, ai_consent, is_ip, ip_released_at,
                      adviser_id, added_by_id)
            ON public.records_record TO iris_authz_verifier;
        GRANT SELECT (id, role_id) ON public.accounts_user TO iris_authz_verifier;
        GRANT SELECT (id, name) ON public.accounts_role TO iris_authz_verifier;
        GRANT SELECT (record_id, user_id) ON public.records_recordowner TO iris_authz_verifier;
    END IF;
END $$"""


class Migration(migrations.Migration):

    dependencies = [
        ("ai", "0051_research_adviser_names"),
    ]

    operations = [
        # Kept on reverse: no migration revokes the verifier's column grants.
        migrations.RunSQL(GRANTS, migrations.RunSQL.noop),
    ]
