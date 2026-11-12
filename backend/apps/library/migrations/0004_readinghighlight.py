import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("library", "0003_readingnote"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ReadingHighlight",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("manuscript_revision", models.UUIDField()),
                ("manuscript_sha256", models.CharField(max_length=64)),
                ("page", models.PositiveIntegerField()),
                ("quote", models.TextField()),
                ("prefix", models.TextField(blank=True, default="")),
                ("suffix", models.TextField(blank=True, default="")),
                ("regions", models.JSONField(blank=True, default=list)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("owner", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="reading_highlights", to=settings.AUTH_USER_MODEL)),
                ("record", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="+", to="records.record")),
            ],
            options={
                "indexes": [models.Index(fields=["owner", "record", "-created_at"], name="library_highlight_idx")],
            },
        ),
    ]
