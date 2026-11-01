"""
Rate limits of their own for sign-in and registration (IR-661).

Each budget belongs to one client address, read the way the lockout reads it.
DRF's own identification trusts the whole `X-Forwarded-For` header unless told
how many proxies there are, so a client could buy a fresh budget per request by
sending a new value.
"""
from rest_framework.throttling import SimpleRateThrottle

from .client_address import client_address


class ClientAddressThrottle(SimpleRateThrottle):
    def get_cache_key(self, request, view):
        return self.cache_format % {"scope": self.scope, "ident": client_address(request)}


class LoginThrottle(ClientAddressThrottle):
    scope = "auth_login"


class RegisterThrottle(ClientAddressThrottle):
    scope = "auth_register"
