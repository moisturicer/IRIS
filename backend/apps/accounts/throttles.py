"""
Rate limits of their own for sign-in and registration (IR-661).

Each budget belongs to one client address, read the way the lockout reads it.
DRF's own identification trusts the whole `X-Forwarded-For` header unless told
how many proxies there are, so a client could buy a fresh budget per request by
sending a new value.
"""
from rest_framework.throttling import SimpleRateThrottle, UserRateThrottle

from .client_address import client_address

# Soft limits (IR-999): each budget has a per-minute burst and a daily backstop.


class ClientAddressThrottle(SimpleRateThrottle):
    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": client_address(request)}


class PersonalDataExportThrottle(UserRateThrottle):
    """A person's own data download (IR-786): a budget of its own, per signed-in person."""

    scope = "personal_data_export"


class LoginBurstThrottle(ClientAddressThrottle):
    scope = "auth_login_burst"


class LoginThrottle(ClientAddressThrottle):
    scope = "auth_login"


class RegisterBurstThrottle(ClientAddressThrottle):
    scope = "auth_register_burst"


class RegisterThrottle(ClientAddressThrottle):
    scope = "auth_register"
