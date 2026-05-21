from .base import *  # noqa

DEBUG = False

SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# TODO: set ALLOWED_HOSTS to real domain
# TODO: configure S3 for MEDIA_ROOT via django-storages
# TODO: configure Sentry DSN
