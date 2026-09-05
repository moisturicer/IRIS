"""
Drop the tables left behind by the removed `apps.storage` app (IR-62 / SC-01).

Removing an app from INSTALLED_APPS does not drop its tables -- Django simply
stops managing them -- so on any database that ran the old migrations,
`storage_storagefolder` and `storage_storagefile` would linger with real rows in
them after the code that guarded (badly) and served them is gone. That is worse
than the original defect: uploaded files with no reachable owner and no code path
that could ever delete them.

This lives in `accounts` rather than in the deleted app because both storage
models held foreign keys to `accounts.User`, and a migration cannot live in a
package that no longer exists.
"""

from django.db import migrations


# `IF EXISTS` is load-bearing, not defensive habit: on a database created after
# this commit the storage tables were never built, and the acceptance criteria
# require the migration to apply cleanly to a fresh database as well as to a
# copy of the existing one.
#
# `storage_storagefile` goes first -- it holds the FK to `storage_storagefolder`.
DROP_STORAGE_TABLES = """
DROP TABLE IF EXISTS storage_storagefile;
DROP TABLE IF EXISTS storage_storagefolder;
DELETE FROM django_migrations WHERE app = 'storage';
"""


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0007_user_consent_given"),
    ]

    operations = [
        migrations.RunSQL(
            sql=DROP_STORAGE_TABLES,
            # Deliberately not reversible in substance. Migrating backwards past
            # this point leaves the tables absent rather than recreating a
            # feature that was removed on purpose; `noop` keeps a reverse
            # migration from erroring instead of silently rebuilding it.
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
