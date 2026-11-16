"""Password rules beyond Django's own (IR-819, ASVS 2.1.2 and 2.1.7).

`AUTH_PASSWORD_VALIDATORS` in `config/settings/base.py` is the one definition of
the policy. Registration, a signed-in change and a reset all apply it through
`validate_password`, so a rule added here holds on all three.
"""

from pathlib import Path

from django.contrib.auth.password_validation import CommonPasswordValidator
from django.core.exceptions import ValidationError

MAX_PASSWORD_LENGTH = 128
BREACHED_LIST = Path(__file__).resolve().parent / "passwords" / "breached-12plus.txt.gz"


class MaximumLengthValidator:
    """At most 128 characters (ASVS 2.1.2). Long passphrases are welcome; a
    megabyte "password" only costs hashing time."""

    def __init__(self, max_length=MAX_PASSWORD_LENGTH):
        self.max_length = max_length

    def validate(self, password, user=None):
        if len(password) > self.max_length:
            raise ValidationError(
                f"This password is too long. It must contain at most {self.max_length} characters.",
                code="password_too_long",
            )

    def get_help_text(self):
        return f"Your password must contain at most {self.max_length} characters."


class BreachedPasswordValidator(CommonPasswordValidator):
    """Refuse a password known from data breaches (ASVS 2.1.7).

    Django's own list covers the common short ones; this one holds breached
    passwords of 12 to 128 characters, the ones the length rule would otherwise
    let through (`passwords/README.md`). Checked locally: nothing is sent
    anywhere.
    """

    DEFAULT_PASSWORD_LIST_PATH = BREACHED_LIST

    def validate(self, password, user=None):
        if password.lower().strip() in self.passwords:
            raise ValidationError(
                "This password has appeared in a data breach. Choose a different one.",
                code="password_breached",
            )

    def get_help_text(self):
        return "Your password can't be one that has appeared in a data breach."
