"""
IR-947: a saved feed's single `year` becomes Discover's from–to range.

Discover now filters by `year_from` and `year_to`, and a feed stores Discover's
own query, so every stored `{"year": "2018"}` becomes
`{"year_from": "2018", "year_to": "2018"}`: the same papers, in the new
spelling. Without this, a feed holding `year` would lose its year filter and
silently widen.

Backwards turns a one-year range back into `year`. A range of several years has
no single-year spelling, so it keeps its start year: narrower, never wider.
"""

from django.db import migrations


def to_range(apps, schema_editor):
    SavedFeed = apps.get_model("library", "SavedFeed")
    for feed in SavedFeed.objects.filter(query__has_key="year"):
        query = dict(feed.query)
        year = query.pop("year")
        query["year_from"] = year
        query["year_to"] = year
        feed.query = query
        feed.save(update_fields=["query"])


def to_single_year(apps, schema_editor):
    SavedFeed = apps.get_model("library", "SavedFeed")
    for feed in SavedFeed.objects.all():
        query = dict(feed.query)
        start, end = query.pop("year_from", None), query.pop("year_to", None)
        if start is None and end is None:
            continue
        query["year"] = start or end
        feed.query = query
        feed.save(update_fields=["query"])


class Migration(migrations.Migration):
    dependencies = [("library", "0007_reading_positions")]

    operations = [migrations.RunPython(to_range, to_single_year)]
