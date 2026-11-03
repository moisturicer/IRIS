"""Permit only the verifier's canonical row lock under update-side RLS."""
from importlib import import_module
from django.db import migrations

previous = import_module('apps.publication.migrations.0006_extraction_write_fence')
FUNCTION = previous.SQL.split('REVOKE ALL')[0].replace('CREATE FUNCTION', 'CREATE OR REPLACE FUNCTION')
FUNCTION = FUNCTION.replace(
    '    -- A fresh statement',
    '    IF NOT FOUND THEN RETURN; END IF;\n    -- A fresh statement')

POLICY = """
CREATE POLICY iris_processing_lock ON public.records_record FOR UPDATE
    USING (current_user = 'iris_authz_verifier')
    WITH CHECK (current_user = 'iris_authz_verifier');
"""


class Migration(migrations.Migration):
    dependencies = [('publication', '0006_extraction_write_fence')]
    operations = [
        migrations.RunSQL(POLICY, 'DROP POLICY iris_processing_lock ON public.records_record;'),
        migrations.RunSQL(FUNCTION, previous.SQL.split('REVOKE ALL')[0].replace(
            'CREATE FUNCTION', 'CREATE OR REPLACE FUNCTION')),
    ]
