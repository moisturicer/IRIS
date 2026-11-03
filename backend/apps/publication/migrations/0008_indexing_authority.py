"""Canonical indexing authority; the AI owner only writes derived datasets."""

from importlib import import_module
from django.db import migrations

old = import_module("apps.publication.migrations.0005_canonical_embargo_stamps")
generation = import_module("apps.publication.migrations.0004_authority_generation")
PREVIOUS = generation.FENCE.replace(old.OLD, old.NEW)
# Summary inputs belong to the same authority generation as document inputs.
FENCE = PREVIOUS.replace(
    "OR to_jsonb(NEW)->'embargo_state'",
    "OR NEW.title IS DISTINCT FROM OLD.title OR NEW.abstract IS DISTINCT FROM OLD.abstract\n           OR NEW.dpa_accepted_at IS DISTINCT FROM OLD.dpa_accepted_at OR NEW.is_ip IS DISTINCT FROM OLD.is_ip\n           OR NEW.ip_released_at IS DISTINCT FROM OLD.ip_released_at\n           OR to_jsonb(NEW)->'embargo_state'",
)
SQL = r"""
CREATE FUNCTION iris_authz.indexing_source() RETURNS TABLE
    (work_id uuid, record_id bigint, revision uuid, generation bigint, title text, abstract text)
LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
    SELECT s.work_id, s.record_id, s.revision, w.authority_generation, r.title::text, r.abstract::text
    FROM iris_authz.processing_source() s
    JOIN public.publication_manuscriptwork w ON w.id=s.work_id
    JOIN public.records_record r ON r.id=s.record_id
    WHERE r.dpa_accepted_at IS NOT NULL AND (NOT r.is_ip OR r.ip_released_at IS NOT NULL)
      AND r.embargo_answered_at IS NOT NULL
      AND (r.embargo_released_at IS NOT NULL OR r.embargoed_until IS NULL)
$$;
CREATE FUNCTION iris_authz.indexed_source_current(p_work uuid, p_revision uuid, p_generation bigint)
RETURNS boolean LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog, pg_temp AS $$
    SELECT EXISTS (
      SELECT 1 FROM public.publication_manuscriptwork w
      JOIN public.records_record r ON r.id=w.record_id
      WHERE w.id=p_work AND w.revision=p_revision AND w.authority_generation=p_generation
        AND w.revoked_at IS NULL AND NOT r.is_deleted AND r.abstract_file=w.source_file
        AND r.dpa_accepted_at IS NOT NULL AND (NOT r.is_ip OR r.ip_released_at IS NOT NULL)
        AND r.embargo_answered_at IS NOT NULL
        AND (r.embargo_released_at IS NOT NULL OR r.embargoed_until IS NULL)
        AND (r.id=ANY(iris_authz.research_record_ids())
             OR EXISTS (SELECT 1 FROM iris_authz.processing_source() s WHERE s.work_id=w.id)))
$$;
REVOKE ALL ON FUNCTION iris_authz.indexing_source(),
    iris_authz.indexed_source_current(uuid,uuid,bigint) FROM PUBLIC;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("publication", "0007_processing_lock_policy"),
        ("records", "0028_record_ip_release"),
    ]
    operations = [
        migrations.RunSQL(FENCE, PREVIOUS),
        migrations.RunSQL(
            SQL,
            "DROP FUNCTION iris_authz.indexing_source(); DROP FUNCTION iris_authz.indexed_source_current(uuid,uuid,bigint);",
        ),
    ]
