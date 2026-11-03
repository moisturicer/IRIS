"""The embargo state is derived; fence the canonical answer/release stamps."""
from importlib import import_module
from django.db import migrations

generation = import_module("apps.publication.migrations.0004_authority_generation")
OLD = "OR to_jsonb(NEW)->'embargo_state' IS DISTINCT FROM to_jsonb(OLD)->'embargo_state'"
NEW = OLD + """
           OR to_jsonb(NEW)->'embargo_answered_at' IS DISTINCT FROM to_jsonb(OLD)->'embargo_answered_at'
           OR to_jsonb(NEW)->'embargoed_until' IS DISTINCT FROM to_jsonb(OLD)->'embargoed_until'
           OR to_jsonb(NEW)->'embargo_released_at' IS DISTINCT FROM to_jsonb(OLD)->'embargo_released_at'"""
if generation.FENCE.count(OLD) != 1:
    raise RuntimeError("IR-737 expected one embargo fence")


class Migration(migrations.Migration):
    dependencies = [("publication", "0004_authority_generation")]
    operations = [migrations.RunSQL(generation.FENCE.replace(OLD, NEW), generation.FENCE)]
