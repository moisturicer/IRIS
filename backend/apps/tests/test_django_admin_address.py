"""Django's admin site lives at /django-admin/, and nothing of Django's at /admin/ (IR-782).

IRIS's own pages live under /admin/ (ADR-051 decision 7), and production nginx
proxies only /django-admin/ to Django, behind IR-668's allowlist. A Django route
under /admin/ would be unreachable in production and would invite someone to
proxy /admin/ again, which sends IRIS's pages to Django on a refresh.
"""

from django.test import SimpleTestCase
from django.urls import Resolver404, resolve


class DjangoAdminAddressTests(SimpleTestCase):
    def test_the_admin_site_is_at_django_admin(self):
        for path in ("/django-admin/", "/django-admin/login/"):
            with self.subTest(path=path):
                self.assertEqual(resolve(path).namespace, "admin")

    def test_nothing_of_djangos_answers_under_admin(self):
        for path in ("/admin/", "/admin/login/", "/admin/users", "/admin/audit"):
            with self.subTest(path=path):
                with self.assertRaises(Resolver404):
                    resolve(path)
