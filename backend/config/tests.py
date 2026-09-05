"""
Project-level tests for routes and apps that have been deliberately removed.

A deletion needs a test as much as an addition does. Without one, nothing stops
a later merge from quietly reinstating `apps.storage` -- and it carried six
endpoints with no ownership check on any of them, so its return would be a
security regression rather than a cosmetic one.

IR-62 / SC-01.
"""

import importlib

from django.conf import settings
from django.test import SimpleTestCase


class StorageAppRemovedTests(SimpleTestCase):
    """
    `apps.storage` was removed rather than secured (IR-62).

    Deleting the app was cheaper than writing six permission classes plus their
    tests for a file browser no pilot workflow touches. These assertions are the
    acceptance criteria of that ticket, kept executable.
    """

    # Every route the app used to serve, from the deleted `apps/storage/urls.py`.
    REMOVED_ROUTES = [
        "/api/v1/storage/",
        "/api/v1/storage/folders/",
        "/api/v1/storage/folders/1/",
        "/api/v1/storage/files/",
        "/api/v1/storage/files/1/",
        "/api/v1/storage/files/1/download/",
    ]

    def test_storage_routes_return_404(self):
        """
        The six former storage endpoints must not resolve.

        404 specifically, not 401/403: a 401 would mean the route still exists
        and is merely gated, which is the state this ticket exists to end.
        """
        for route in self.REMOVED_ROUTES:
            with self.subTest(route=route):
                response = self.client.get(route)
                self.assertEqual(
                    response.status_code,
                    404,
                    f"{route} still resolves (got {response.status_code}); "
                    "apps.storage appears to have been reinstated",
                )

    def test_storage_not_in_installed_apps(self):
        self.assertNotIn("apps.storage", settings.INSTALLED_APPS)

    def test_storage_package_does_not_exist(self):
        with self.assertRaises(ModuleNotFoundError):
            importlib.import_module("apps.storage")
