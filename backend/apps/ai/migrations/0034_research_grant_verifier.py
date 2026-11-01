"""The research-grant verifier, inside PostgreSQL (IR-717, ADR-049 §6-7).

Schema `iris_authz` holds the HMAC keys and SECURITY DEFINER functions with
a pinned search path. Nothing in it is granted to PUBLIC; roles and function
ownership are set by `manage.py provision_research_roles`, keys by
`manage.py install_research_grant_keys`. No Django model changes.
"""

from django.db import migrations

FORWARD = r"""
CREATE SCHEMA IF NOT EXISTS iris_authz;
REVOKE ALL ON SCHEMA iris_authz FROM PUBLIC;

CREATE TABLE iris_authz.grant_key (
    kid        text PRIMARY KEY CHECK (kid ~ '^[A-Za-z0-9_-]{1,32}$'),
    secret     bytea NOT NULL CHECK (length(secret) >= 32),
    audience   text NOT NULL,
    deployment text NOT NULL,
    -- NULL for the signing key; a retired key verifies only until then.
    retire_at  timestamptz
);
REVOKE ALL ON iris_authz.grant_key FROM PUBLIC;

-- RFC 2104 over the built-in sha256(), so no extension is needed.
CREATE FUNCTION iris_authz.hmac_sha256(p_key bytea, p_msg bytea) RETURNS bytea
LANGUAGE plpgsql IMMUTABLE STRICT
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
    k bytea := p_key;
    ipad bytea;
    opad bytea;
    i int;
BEGIN
    IF length(k) > 64 THEN k := sha256(k); END IF;
    k := k || decode(repeat('00', 64 - length(k)), 'hex');
    ipad := k;
    opad := k;
    FOR i IN 0..63 LOOP
        ipad := set_byte(ipad, i, get_byte(k, i) # 54);
        opad := set_byte(opad, i, get_byte(k, i) # 92);
    END LOOP;
    RETURN sha256(opad || sha256(ipad || p_msg));
END
$$;

CREATE FUNCTION iris_authz.b64url_encode(p bytea) RETURNS text
LANGUAGE sql IMMUTABLE STRICT
SET search_path = pg_catalog, pg_temp
AS $$ SELECT rtrim(translate(replace(encode(p, 'base64'), E'\n', ''), '+/', '-_'), '=') $$;

CREATE FUNCTION iris_authz.b64url_decode(p text) RETURNS bytea
LANGUAGE sql IMMUTABLE STRICT
SET search_path = pg_catalog, pg_temp
AS $$ SELECT decode(translate(p, '-_', '+/') || repeat('=', (4 - length(p) % 4) % 4), 'base64') $$;

CREATE FUNCTION iris_authz.verify_research_grant(p_grant text, p_purpose text) RETURNS jsonb
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

-- A tag only the verifier can compute, tying the setting to one transaction.
CREATE FUNCTION iris_authz.binding_tag(p_grant text, p_purpose text) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
    s bytea;
BEGIN
    SELECT secret INTO s FROM iris_authz.grant_key
     WHERE kid = split_part(p_grant, '.', 2) AND (retire_at IS NULL OR retire_at > clock_timestamp());
    IF NOT FOUND THEN RETURN NULL; END IF;
    RETURN encode(iris_authz.hmac_sha256(s, convert_to(
        'bind:' || p_purpose || ':' || txid_current()::text || ':' || pg_backend_pid()::text
        || ':' || p_grant, 'UTF8')), 'hex');
END
$$;

CREATE FUNCTION iris_authz.current_research_claims() RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
    g text := nullif(current_setting('iris.research_grant', true), '');
    p text := nullif(current_setting('iris.research_purpose', true), '');
    b text := nullif(current_setting('iris.research_bind', true), '');
    claims jsonb;
BEGIN
    IF g IS NULL OR p IS NULL OR b IS NULL THEN RETURN NULL; END IF;
    IF iris_authz.binding_tag(g, p) IS DISTINCT FROM b THEN RETURN NULL; END IF;
    claims := iris_authz.verify_research_grant(g, p);
    RETURN claims;
END
$$;

CREATE FUNCTION iris_authz.current_reader() RETURNS bigint
LANGUAGE sql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$ SELECT (iris_authz.current_research_claims()->>'sub')::bigint $$;

CREATE FUNCTION iris_authz.begin_research(p_grant text, p_purpose text) RETURNS jsonb
LANGUAGE plpgsql SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
    claims jsonb := iris_authz.verify_research_grant(p_grant, p_purpose);
    bound text := nullif(current_setting('iris.research_grant', true), '');
BEGIN
    IF claims IS NULL THEN
        RAISE EXCEPTION 'research grant rejected' USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF bound IS NOT NULL AND iris_authz.current_research_claims() IS NOT NULL
       AND (bound <> p_grant OR current_setting('iris.research_purpose', true) <> p_purpose) THEN
        RAISE EXCEPTION 'research identity already bound in this transaction'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    PERFORM set_config('iris.research_grant', p_grant, true);
    PERFORM set_config('iris.research_purpose', p_purpose, true);
    PERFORM set_config('iris.research_bind', iris_authz.binding_tag(p_grant, p_purpose), true);
    RETURN claims;
END
$$;

REVOKE ALL ON ALL FUNCTIONS IN SCHEMA iris_authz FROM PUBLIC;
"""

REVERSE = "DROP SCHEMA IF EXISTS iris_authz CASCADE;"


class Migration(migrations.Migration):

    dependencies = [
        ("ai", "0033_chat_request_identity"),
        ("accounts", "0014_account_recovery"),
    ]

    operations = [migrations.RunSQL(FORWARD, REVERSE)]
