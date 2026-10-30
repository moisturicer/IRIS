"""Explicit, atomic administrative corrections; never an inferred backfill."""
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from rest_framework import serializers

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.records.models import Author, Record


class Correction(serializers.Serializer):
    id = serializers.IntegerField(min_value=1)
    origin = serializers.ChoiceField(choices=Record.Origin.choices, required=False)
    publication_year = serializers.IntegerField(min_value=1, max_value=9999, allow_null=True, required=False)
    authors = serializers.ListField(child=serializers.CharField(max_length=200), max_length=100, required=False)
    evidence = serializers.CharField(max_length=2000)

    def validate(self, attrs):
        extra = set(self.initial_data) - set(self.fields)
        if extra:
            raise serializers.ValidationError(f"Unsupported fields: {', '.join(sorted(extra))}")
        if not {"origin", "publication_year", "authors"}.intersection(attrs):
            raise serializers.ValidationError("Declare at least one metadata correction.")
        return attrs


def snapshot(record):
    return {
        "origin": record.origin, "publication_year": record.publication_year,
        "authors": list(record.authors.order_by("pk").values_list("name", flat=True)),
    }


class Command(BaseCommand):
    help = "Correct declared origin, publication year and/or authors by record ID from verified JSON."

    def add_arguments(self, parser):
        parser.add_argument("manifest")
        parser.add_argument("--actor", required=True, help="Email of the active superuser authorizing the correction.")
        parser.add_argument("--reason", required=True)
        parser.add_argument("--dry-run", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        actor = User.objects.filter(email__iexact=options["actor"], is_active=True, is_superuser=True).first()
        if actor is None:
            raise CommandError("An active superuser actor is required.")
        reason = options["reason"].strip()
        if not reason:
            raise CommandError("A correction reason is required.")
        try:
            rows = json.loads(Path(options["manifest"]).read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            raise CommandError(f"Cannot read metadata manifest: {exc}") from exc
        if not isinstance(rows, list) or not rows:
            raise CommandError("The manifest must be a non-empty JSON array.")
        validated = []
        seen = set()
        for index, row in enumerate(rows, start=1):
            serializer = Correction(data=row)
            if not serializer.is_valid():
                raise CommandError(f"Row {index}: {serializer.errors}")
            data = serializer.validated_data
            if data["id"] in seen:
                raise CommandError(f"Duplicate record ID: {data['id']}")
            seen.add(data["id"])
            validated.append(data)
        records = Record.objects.select_for_update().in_bulk(seen)
        if set(records) != seen:
            raise CommandError("Every record ID must exist; no corrections were applied.")
        # The whole manifest has been validated and every target locked before writing.
        if not options["dry_run"]:
            for row in validated:
                record = records[row["id"]]
                before = snapshot(record)
                for field in ("origin", "publication_year"):
                    if field in row:
                        setattr(record, field, row[field])
                record.save(update_fields=["origin", "publication_year", "updated_at"])
                if "authors" in row:
                    record.authors.all().delete()
                    Author.objects.bulk_create([Author(record=record, name=name) for name in row["authors"]])
                AuditEvent.objects.create(
                    event_type=AuditEvent.RESEARCH_METADATA_CORRECTED, user=actor, record=record,
                    metadata={"reason": reason, "evidence": row["evidence"], "before": before, "after": snapshot(record)},
                )
        verb = "Validated" if options["dry_run"] else "Corrected"
        self.stdout.write(f"{verb} {len(validated)} record(s).")
