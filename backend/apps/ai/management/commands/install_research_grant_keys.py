"""Install the configured research-grant keys into the verifier (IR-717).

Run with maintenance credentials whenever AI_RESEARCH_GRANT_KEYS changes.
The active key signs and verifies with no end date. Every other configured
key only verifies, and only for one grant lifetime from the first install
that found it inactive: that is the bounded rotation overlap. A key no
longer configured is removed at once.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from apps.ai.grants import config


class Command(BaseCommand):
    help = "Install research-grant verification keys into PostgreSQL (IR-717)."

    def handle(self, *args, **options):
        try:
            cfg = config.read()
        except config.GrantsUnavailable:
            raise CommandError("AI_RESEARCH_GRANTS must be on and fully configured")
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute("DELETE FROM iris_authz.grant_key WHERE NOT (kid = ANY(%s))", [list(cfg.keys)])
            for kid, secret in cfg.keys.items():
                active = kid == cfg.active_kid
                cursor.execute(
                    """INSERT INTO iris_authz.grant_key (kid, secret, audience, deployment, retire_at)
                       VALUES (%s, %s, %s, %s,
                               CASE WHEN %s THEN NULL ELSE now() + make_interval(secs => %s) END)
                       ON CONFLICT (kid) DO UPDATE SET
                         secret = EXCLUDED.secret, audience = EXCLUDED.audience,
                         deployment = EXCLUDED.deployment,
                         retire_at = CASE WHEN %s THEN NULL
                                          ELSE LEAST(COALESCE(iris_authz.grant_key.retire_at, 'infinity'),
                                                     EXCLUDED.retire_at) END""",
                    [kid, secret, cfg.audience, cfg.deployment, active, cfg.ttl_seconds, active],
                )
        retiring = len(cfg.keys) - 1
        self.stdout.write(f"research grant keys installed: active {cfg.active_kid}, {retiring} retiring")
