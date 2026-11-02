"""A reader session for the AI runtime's own runs (IR-722, ADR-049 §6).

Adds the `reader_session` purpose to the verifier: the reader and their
credential generation, bound to no run, Conversation or Record. IR-718's
policy reads no Record for it. `reader_status()` lets the AI runtime fence
a departed reader's runs, and purge a deleted account's Conversations,
without reading `accounts_user`.

CREATE OR REPLACE keeps the function's owner and grants; re-run
`manage.py provision_research_roles` afterwards to grant `reader_status()`.
"""

from django.db import migrations

VERIFY = r"""
CREATE OR REPLACE FUNCTION iris_authz.verify_research_grant(p_grant text, p_purpose text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
    parts text[];
    k record;
    claims jsonb;
    now_epoch numeric := extract(epoch FROM clock_timestamp());
    iat numeric;
    exp numeric;
    u record;
    r record;
    j record;
BEGIN
    IF p_grant IS NULL OR p_purpose IS NULL OR length(p_grant) > 4096 THEN RETURN NULL; END IF;
    parts := string_to_array(p_grant, '.');
    IF array_length(parts, 1) <> 4 OR parts[1] <> 'irg1' OR parts[3] !~ '^[A-Za-z0-9_-]+$' THEN
        RETURN NULL;
    END IF;
    SELECT * INTO k FROM iris_authz.grant_key
     WHERE kid = parts[2] AND (retire_at IS NULL OR retire_at > clock_timestamp());
    IF NOT FOUND THEN RETURN NULL; END IF;
    IF iris_authz.b64url_encode(iris_authz.hmac_sha256(
           k.secret, convert_to(parts[1] || '.' || parts[2] || '.' || parts[3], 'UTF8'))) <> parts[4] THEN
        RETURN NULL;
    END IF;

    claims := convert_from(iris_authz.b64url_decode(parts[3]), 'UTF8')::jsonb;
    IF jsonb_typeof(claims) <> 'object'
       OR claims->>'kid' IS DISTINCT FROM k.kid
       OR claims->>'aud' IS DISTINCT FROM k.audience
       OR claims->>'dep' IS DISTINCT FROM k.deployment
       OR claims->>'pur' IS DISTINCT FROM p_purpose THEN
        RETURN NULL;
    END IF;
    iat := (claims->>'iat')::numeric;
    exp := (claims->>'exp')::numeric;
    IF iat IS NULL OR exp IS NULL OR iat > now_epoch + 30 OR exp <= now_epoch OR exp - iat > 900 THEN
        RETURN NULL;
    END IF;

    IF p_purpose IN ('record_read', 'reader_run', 'reader_session') THEN
        SELECT id, is_active, is_locked, credential_version INTO u
          FROM public.accounts_user WHERE id = (claims->>'sub')::bigint;
        IF NOT FOUND OR NOT u.is_active OR u.is_locked
           OR u.credential_version IS DISTINCT FROM (claims->>'gen')::bigint THEN
            RETURN NULL;
        END IF;
    END IF;

    IF p_purpose = 'record_read' THEN
        IF claims->>'run' IS NOT NULL OR claims->>'cnv' IS NOT NULL OR claims->>'job' IS NOT NULL THEN
            RETURN NULL;
        END IF;
    ELSIF p_purpose = 'reader_session' THEN
        IF claims->>'run' IS NOT NULL OR claims->>'cnv' IS NOT NULL OR claims->>'rec' IS NOT NULL
           OR claims->>'job' IS NOT NULL OR claims->>'rev' IS NOT NULL THEN
            RETURN NULL;
        END IF;
    ELSIF p_purpose = 'reader_run' THEN
        SELECT a.state, a.deadline_at, a.user_id, a.conversation_id,
               c.user_id AS conversation_user, c.record_id
          INTO r
          FROM public.ai_askrun a JOIN public.ai_conversation c ON c.id = a.conversation_id
         WHERE a.id = (claims->>'run')::uuid;
        IF NOT FOUND
           OR r.user_id <> u.id OR r.conversation_user <> u.id
           OR r.conversation_id IS DISTINCT FROM (claims->>'cnv')::bigint
           OR r.record_id IS DISTINCT FROM (claims->>'rec')::bigint
           OR r.state NOT IN ('queued', 'running')
           OR r.deadline_at <= clock_timestamp()
           OR exp > extract(epoch FROM r.deadline_at) THEN
            RETURN NULL;
        END IF;
    ELSIF p_purpose = 'ingestion' THEN
        IF claims->>'sub' IS NOT NULL OR claims->>'run' IS NOT NULL THEN RETURN NULL; END IF;
        SELECT record_id, extraction_hash INTO j
          FROM public.ai_ingestionjob WHERE id = (claims->>'job')::bigint;
        IF NOT FOUND
           OR j.record_id IS DISTINCT FROM (claims->>'rec')::bigint
           OR j.extraction_hash IS DISTINCT FROM claims->>'rev' THEN
            RETURN NULL;
        END IF;
    ELSE
        RETURN NULL;
    END IF;
    RETURN claims;
EXCEPTION WHEN others THEN
    RETURN NULL;
END
$$;
"""

#: `active`, `inactive` (deactivated or locked) or `gone` (deleted).
READER_STATUS = r"""
CREATE FUNCTION iris_authz.reader_status(p_reader bigint) RETURNS text
LANGUAGE sql STABLE SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
    SELECT coalesce((SELECT CASE WHEN is_active AND NOT is_locked THEN 'active' ELSE 'inactive' END
                       FROM public.accounts_user WHERE id = p_reader), 'gone')
$$;
REVOKE ALL ON FUNCTION iris_authz.reader_status(bigint) FROM PUBLIC;
"""

#: 0034's verifier, restored on reverse.
PREVIOUS_VERIFY = r"""
CREATE OR REPLACE FUNCTION iris_authz.verify_research_grant(p_grant text, p_purpose text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
    parts text[];
    k record;
    claims jsonb;
    now_epoch numeric := extract(epoch FROM clock_timestamp());
    iat numeric;
    exp numeric;
    u record;
    r record;
    j record;
BEGIN
    IF p_grant IS NULL OR p_purpose IS NULL OR length(p_grant) > 4096 THEN RETURN NULL; END IF;
    parts := string_to_array(p_grant, '.');
    IF array_length(parts, 1) <> 4 OR parts[1] <> 'irg1' OR parts[3] !~ '^[A-Za-z0-9_-]+$' THEN
        RETURN NULL;
    END IF;
    SELECT * INTO k FROM iris_authz.grant_key
     WHERE kid = parts[2] AND (retire_at IS NULL OR retire_at > clock_timestamp());
    IF NOT FOUND THEN RETURN NULL; END IF;
    IF iris_authz.b64url_encode(iris_authz.hmac_sha256(
           k.secret, convert_to(parts[1] || '.' || parts[2] || '.' || parts[3], 'UTF8'))) <> parts[4] THEN
        RETURN NULL;
    END IF;

    claims := convert_from(iris_authz.b64url_decode(parts[3]), 'UTF8')::jsonb;
    IF jsonb_typeof(claims) <> 'object'
       OR claims->>'kid' IS DISTINCT FROM k.kid
       OR claims->>'aud' IS DISTINCT FROM k.audience
       OR claims->>'dep' IS DISTINCT FROM k.deployment
       OR claims->>'pur' IS DISTINCT FROM p_purpose THEN
        RETURN NULL;
    END IF;
    iat := (claims->>'iat')::numeric;
    exp := (claims->>'exp')::numeric;
    IF iat IS NULL OR exp IS NULL OR iat > now_epoch + 30 OR exp <= now_epoch OR exp - iat > 900 THEN
        RETURN NULL;
    END IF;

    IF p_purpose IN ('record_read', 'reader_run') THEN
        SELECT id, is_active, is_locked, credential_version INTO u
          FROM public.accounts_user WHERE id = (claims->>'sub')::bigint;
        IF NOT FOUND OR NOT u.is_active OR u.is_locked
           OR u.credential_version IS DISTINCT FROM (claims->>'gen')::bigint THEN
            RETURN NULL;
        END IF;
    END IF;

    IF p_purpose = 'record_read' THEN
        IF claims->>'run' IS NOT NULL OR claims->>'cnv' IS NOT NULL OR claims->>'job' IS NOT NULL THEN
            RETURN NULL;
        END IF;
    ELSIF p_purpose = 'reader_run' THEN
        SELECT a.state, a.deadline_at, a.user_id, a.conversation_id,
               c.user_id AS conversation_user, c.record_id
          INTO r
          FROM public.ai_askrun a JOIN public.ai_conversation c ON c.id = a.conversation_id
         WHERE a.id = (claims->>'run')::uuid;
        IF NOT FOUND
           OR r.user_id <> u.id OR r.conversation_user <> u.id
           OR r.conversation_id IS DISTINCT FROM (claims->>'cnv')::bigint
           OR r.record_id IS DISTINCT FROM (claims->>'rec')::bigint
           OR r.state NOT IN ('queued', 'running')
           OR r.deadline_at <= clock_timestamp()
           OR exp > extract(epoch FROM r.deadline_at) THEN
            RETURN NULL;
        END IF;
    ELSIF p_purpose = 'ingestion' THEN
        IF claims->>'sub' IS NOT NULL OR claims->>'run' IS NOT NULL THEN RETURN NULL; END IF;
        SELECT record_id, extraction_hash INTO j
          FROM public.ai_ingestionjob WHERE id = (claims->>'job')::bigint;
        IF NOT FOUND
           OR j.record_id IS DISTINCT FROM (claims->>'rec')::bigint
           OR j.extraction_hash IS DISTINCT FROM claims->>'rev' THEN
            RETURN NULL;
        END IF;
    ELSE
        RETURN NULL;
    END IF;
    RETURN claims;
EXCEPTION WHEN others THEN
    RETURN NULL;
END
$$;
"""


class Migration(migrations.Migration):

    dependencies = [("ai", "0035_research_read_policy")]

    operations = [
        migrations.RunSQL(VERIFY, PREVIOUS_VERIFY),
        migrations.RunSQL(READER_STATUS, "DROP FUNCTION IF EXISTS iris_authz.reader_status(bigint);"),
    ]
