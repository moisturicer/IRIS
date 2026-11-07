"""Create the restricted research roles (IR-717, IR-718).

Run after migrate with maintenance credentials (CREATEROLE or superuser).
Idempotent; `--check` changes nothing.

- `iris_authz_verifier` owns the verifier; reads keys and needed columns.
- `iris_ai_runtime`, `iris_django_runtime`: bind identity, SELECT the
  protected tables; no keys, no ownership, no RLS bypass.

`--force-row-security` is the cutover: FORCE RLS on protected tables.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from apps.ai.grants.policy import PROTECTED_TABLES

VERIFIER = "iris_authz_verifier"
RUNTIME_ROLES = ("iris_ai_runtime", "iris_django_runtime")
ROLE_FLAGS = "NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS"
#: What a CREATEROLE login may reset; `problems()` checks the rest.
NONSUPERUSER_FLAGS = "NOLOGIN NOCREATEROLE"

DEFINER_FUNCTIONS = (
    "verify_research_grant(text, text)",
    "binding_tag(text, text)",
    "current_research_claims()",
    "current_reader()",
    "begin_research(text, text)",
    "research_record_ids()",
    "reader_status(bigint)",
    "indexing_source()",
    "indexed_source_current(uuid,uuid,bigint)",
    "processing_source()",
    "lock_processing_source()",
    "pending_manuscript_work(integer, uuid)",
    "manuscript_invalidations(integer, uuid)",
)
HELPER_FUNCTIONS = ("hmac_sha256(bytea, bytea)", "b64url_encode(bytea)", "b64url_decode(text)")
RUNTIME_FUNCTIONS = (
    "begin_research(text, text)", "current_research_claims()", "current_reader()",
    # Row policies call it as the invoker (IR-718).
    "research_record_ids()",
)
#: Provider admission's ledger, shared by both runtimes (IR-725), and the
#: columns the AI runtime may update: settlement and totals, never a reservation.
LEDGER_TABLES = {
    "ai_providercampaign": "charged_attempts, charged_input_tokens, charged_output_tokens,"
                           " charged_cost_micros, charged_active_ms",
    "ai_providerreservation": "state, settled_at, sent, usage_reported, charge_attempts,"
                              " charge_input_tokens, charge_output_tokens, charge_cost_micros,"
                              " charge_active_ms",
}
# Non-content metadata is read-only, without per-reader row filtering.
RUNTIME_METADATA_TABLES = (
    "ai_embeddingspace",
    # Catalogue vocabulary the AI runtime counts by (IR-750); names, no Record.
    "records_classification", "records_pscedclassification", "records_recordtype",
)
#: Columns the verifier reads, and nothing else (no password hashes).
VERIFIER_COLUMNS = {
    # deleted_at: reader_status() reads a deleted account as `gone` (ai/0043, IR-785).
    "accounts_user": "id, is_active, is_locked, credential_version, role_id, deleted_at",
    "accounts_role": "id, name",
    "records_record": "id, is_deleted, pipeline_status, adviser_id, abstract_file, title, abstract, dpa_accepted_at, is_ip, ip_released_at, "
                      "is_embargoed, embargo_answered_at, embargo_released_at, embargoed_until",
    "publication_manuscriptwork": "id, record_id, revision, source_file, operation, revoked_at,"
                                  " created_at, grant_token, grant_expires_at, authority_generation",
    "publication_manuscriptinvalidation": "id, record_id, work_id, reason, authority_generation",
    "records_recordowner": "record_id, user_id",
    "ai_askrun": "id, state, deadline_at, user_id, conversation_id",
    "ai_conversation": "id, user_id, record_id",
    "ai_ingestionjob": "id, record_id, extraction_hash",
}


def problems(cursor) -> list[str]:
    found = []
    for role in (VERIFIER, *RUNTIME_ROLES):
        cursor.execute(
            "SELECT rolsuper, rolbypassrls, rolcreaterole, rolcanlogin FROM pg_roles WHERE rolname = %s",
            [role],
        )
        row = cursor.fetchone()
        if row is None:
            found.append(f"role {role} does not exist")
        elif any(row):
            found.append(f"role {role} must be NOSUPERUSER NOBYPASSRLS NOCREATEROLE NOLOGIN")
    cursor.execute(
        """SELECT r.rolname, c.relname FROM pg_class c JOIN pg_roles r ON r.oid = c.relowner
            WHERE r.rolname = ANY(%s) AND c.relkind IN ('r', 'p', 'v', 'm')""",
        [list((VERIFIER, *RUNTIME_ROLES))],
    )
    found += [f"role {role} owns {rel}" for role, rel in cursor.fetchall()]
    for role in RUNTIME_ROLES:
        cursor.execute(
            "SELECT 1 FROM pg_roles WHERE rolname = %s", [role]
        )
        if cursor.fetchone() is None:
            continue
        cursor.execute(
            "SELECT has_table_privilege(%s, 'iris_authz.grant_key', 'SELECT')", [role]
        )
        if cursor.fetchone()[0]:
            found.append(f"role {role} can read iris_authz.grant_key")
    cursor.execute(
        """SELECT p.proname FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
            JOIN pg_roles r ON r.oid = p.proowner
            WHERE n.nspname = 'iris_authz' AND p.prosecdef AND r.rolname <> %s""",
        [VERIFIER],
    )
    found += [f"function iris_authz.{name} is not owned by {VERIFIER}" for (name,) in cursor.fetchall()]
    found += _policy_problems(cursor)
    cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = 'iris_ai_runtime'")
    if cursor.fetchone() is not None:
        for table in RUNTIME_METADATA_TABLES:
            cursor.execute(
                "SELECT has_table_privilege('iris_ai_runtime', %s, 'SELECT')", [f"public.{table}"]
            )
            if not cursor.fetchone()[0]:
                found.append(f"role iris_ai_runtime cannot read {table}")
        for table in LEDGER_TABLES:
            cursor.execute(
                "SELECT has_table_privilege('iris_ai_runtime', %s, 'DELETE, TRUNCATE')",
                [f"public.{table}"],
            )
            if cursor.fetchone()[0]:
                found.append(f"role iris_ai_runtime can delete from {table}")
        cursor.execute(
            "SELECT has_column_privilege('iris_ai_runtime', 'public.ai_providerreservation',"
            " 'reserved_cost_micros', 'UPDATE')"
        )
        if cursor.fetchone()[0]:
            found.append("role iris_ai_runtime can rewrite reservations")
    return found


def _policy_problems(cursor) -> list[str]:
    """IR-718: every protected table is row-secured and read-only to runtime roles."""
    found = []
    cursor.execute(
        """SELECT c.relname, c.relrowsecurity,
                  EXISTS (SELECT 1 FROM pg_policy p
                           WHERE p.polrelid = c.oid AND p.polname = 'iris_research_read')
             FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relname = ANY(%s)""",
        [list(PROTECTED_TABLES)],
    )
    rows = {name: (secured, policy) for name, secured, policy in cursor.fetchall()}
    for table in PROTECTED_TABLES:
        secured, policy = rows.get(table, (False, False))
        if not secured:
            found.append(f"{table} has no row security")
        if not policy:
            found.append(f"{table} has no iris_research_read policy")
    for role in RUNTIME_ROLES:
        cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", [role])
        if cursor.fetchone() is None:
            continue
        for table in PROTECTED_TABLES:
            if table not in rows:
                continue
            cursor.execute(
                "SELECT has_table_privilege(%s, %s, 'INSERT, UPDATE, DELETE, TRUNCATE')",
                [role, f"public.{table}"],
            )
            if cursor.fetchone()[0]:
                found.append(f"role {role} can write {table}")
    return found


class Command(BaseCommand):
    help = "Create the restricted research database roles (IR-717)."

    def add_arguments(self, parser):
        parser.add_argument("--check", action="store_true", help="Report problems; change nothing.")
        parser.add_argument(
            "--force-row-security", action="store_true",
            help="Also FORCE row security on research tables (cutover; IR-718). "
                 "The application must no longer connect as their owner.",
        )

    def handle(self, *args, check=False, force_row_security=False, **options):
        with connection.cursor() as cursor:
            if check:
                found = problems(cursor)
                for line in found:
                    self.stdout.write(f"PROBLEM: {line}")
                if found:
                    raise CommandError(f"{len(found)} problem(s)")
                self.stdout.write("research roles: ok")
                return
            cursor.execute(
                "SELECT rolsuper, rolcreaterole FROM pg_roles WHERE rolname = current_user"
            )
            superuser, createrole = cursor.fetchone()
            if not (superuser or createrole):
                raise CommandError("needs maintenance credentials with CREATEROLE (IR-717)")
            with transaction.atomic():
                self._provision(cursor, superuser)
                if force_row_security:
                    self._force(cursor)
            found = problems(cursor)
            if found:
                raise CommandError("; ".join(found))
        self.stdout.write("research roles provisioned")

    def _force(self, cursor):
        cursor.execute("SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user")
        if not cursor.fetchone()[0]:
            # FORCE would filter this maintenance login too.
            raise CommandError("--force-row-security needs a superuser or BYPASSRLS maintenance login")
        for table in PROTECTED_TABLES:
            cursor.execute(f"ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY")
        self.stdout.write(f"row security forced on {len(PROTECTED_TABLES)} tables")

    def _provision(self, cursor, superuser):
        for role in (VERIFIER, *RUNTIME_ROLES):
            cursor.execute(
                f"""DO $$ BEGIN
                    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                        CREATE ROLE {role} {ROLE_FLAGS};
                    END IF;
                END $$"""
            )
            cursor.execute(f"ALTER ROLE {role} {ROLE_FLAGS if superuser else NONSUPERUSER_FLAGS}")
        if not superuser:
            # Needed to hand the functions over; revoked below.
            cursor.execute(f"GRANT {VERIFIER} TO current_user")
        cursor.execute(f"GRANT USAGE ON SCHEMA iris_authz, public TO {VERIFIER}")
        cursor.execute(f"GRANT SELECT ON iris_authz.grant_key TO {VERIFIER}")
        for table, columns in VERIFIER_COLUMNS.items():
            cursor.execute(f"GRANT SELECT ({columns}) ON public.{table} TO {VERIFIER}")
        # PostgreSQL row locks require UPDATE on at least one column.
        cursor.execute(f"GRANT UPDATE (id) ON public.records_record TO {VERIFIER}")
        for fn in HELPER_FUNCTIONS:
            cursor.execute(f"GRANT EXECUTE ON FUNCTION iris_authz.{fn} TO {VERIFIER}")
        for fn in DEFINER_FUNCTIONS:
            cursor.execute(f"ALTER FUNCTION iris_authz.{fn} OWNER TO {VERIFIER}")
            cursor.execute(f"REVOKE ALL ON FUNCTION iris_authz.{fn} FROM PUBLIC")
        for role in RUNTIME_ROLES:
            cursor.execute(f"REVOKE ALL ON iris_authz.grant_key FROM {role}")
            cursor.execute(f"GRANT USAGE ON SCHEMA iris_authz TO {role}")
            for fn in RUNTIME_FUNCTIONS:
                cursor.execute(f"GRANT EXECUTE ON FUNCTION iris_authz.{fn} TO {role}")
        for role in RUNTIME_ROLES:
            for table in PROTECTED_TABLES:
                cursor.execute(f"GRANT SELECT ON public.{table} TO {role}")
        # Restore Django-owned metadata grants after historical table recreation,
        # even when independent AI schema migrations are already recorded.
        for table in RUNTIME_METADATA_TABLES:
            cursor.execute(f"GRANT SELECT ON public.{table} TO iris_ai_runtime")
        # The AI runtime fences a departed reader's runs (IR-722).
        cursor.execute(
            "GRANT EXECUTE ON FUNCTION iris_authz.reader_status(bigint) TO iris_ai_runtime"
        )
        cursor.execute("GRANT EXECUTE ON FUNCTION iris_authz.processing_source(),"
                       " iris_authz.pending_manuscript_work(integer, uuid),"
                       " iris_authz.manuscript_invalidations(integer, uuid),"
                       " iris_authz.lock_processing_source(), iris_authz.indexing_source(),"
                       " iris_authz.indexed_source_current(uuid,uuid,bigint) TO iris_ai_runtime")
        # The AI runtime reserves and settles in the one shared ledger (IR-725).
        for table, columns in LEDGER_TABLES.items():
            cursor.execute(f"REVOKE UPDATE ON public.{table} FROM iris_ai_runtime")
            cursor.execute(f"GRANT SELECT, INSERT ON public.{table} TO iris_ai_runtime")
            cursor.execute(f"GRANT UPDATE ({columns}) ON public.{table} TO iris_ai_runtime")
            cursor.execute(f"GRANT USAGE ON SEQUENCE public.{table}_id_seq TO iris_ai_runtime")
        # Django renews grants, so it alone may ask whether one verifies.
        cursor.execute(
            "GRANT EXECUTE ON FUNCTION iris_authz.verify_research_grant(text, text) TO iris_django_runtime"
        )
        if not superuser:
            # No standing way into the verifier's key read or RLS bypass.
            cursor.execute(f"REVOKE {VERIFIER} FROM current_user")
