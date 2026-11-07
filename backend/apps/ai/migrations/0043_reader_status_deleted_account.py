"""A deleted account reads as `gone` to the AI runtime (IR-785, ADR-051 §11).

Account deletion keeps the `User` row and stamps `deleted_at`, so 0036's
`reader_status()` would read the account as `inactive`: the runtime would fence
its Conversations but `python -m ai.runs.purge` would never delete them. ADR-051
§11 deletes a deleted person's Ask IRIS conversations and research runs, so a
stamped account is `gone`, exactly like a row that no longer exists. This only
narrows: no account that was refused before is admitted now.
"""

from django.db import migrations

READER_STATUS = r"""
CREATE OR REPLACE FUNCTION iris_authz.reader_status(p_reader bigint) RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
    SELECT coalesce((SELECT CASE WHEN deleted_at IS NOT NULL THEN 'gone'
                                 WHEN is_active AND NOT is_locked THEN 'active'
                                 ELSE 'inactive' END
                       FROM public.accounts_user WHERE id = p_reader), 'gone')
$$;
REVOKE ALL ON FUNCTION iris_authz.reader_status(bigint) FROM PUBLIC;
"""

#: 0036's body, restored on reverse.
PREVIOUS_READER_STATUS = r"""
CREATE OR REPLACE FUNCTION iris_authz.reader_status(p_reader bigint) RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
    SELECT coalesce((SELECT CASE WHEN is_active AND NOT is_locked THEN 'active' ELSE 'inactive' END
                       FROM public.accounts_user WHERE id = p_reader), 'gone')
$$;
REVOKE ALL ON FUNCTION iris_authz.reader_status(bigint) FROM PUBLIC;
"""


class Migration(migrations.Migration):

    dependencies = [
        ("ai", "0042_record_space_embedding_read_policy"),
        ("accounts", "0019_account_deletion"),
    ]

    operations = [
        migrations.RunSQL(READER_STATUS, PREVIOUS_READER_STATUS),
    ]
