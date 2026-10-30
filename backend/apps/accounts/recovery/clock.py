"""The recovery clock, a seam so tests can move it without moving the world."""

from django.utils import timezone


def now():
    return timezone.now()
