"""Keep legacy verification links out of request/server logs (ADR-045)."""

import logging
import re


class RecoveryRedaction(logging.Filter):
    def filter(self, record):
        message = record.getMessage()
        record.msg = re.sub(
            r"/(?:api/v1/auth/)?activate/[^\s\"'<>]+",
            "/activate/[redacted]", message,
        )
        record.args = ()
        return True
