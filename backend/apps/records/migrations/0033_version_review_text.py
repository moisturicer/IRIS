"""
IR-871, ADR-058 §1 as amended 2026-11-05: each Version's review text.

Schema only. Existing Versions get no text here: reading a PDF is not a
migration's work, and it needs the sandbox. `manage.py read_review_texts` reads
each from its own manuscript file afterwards, and until then they read
"vN's text hasn't been read yet". Nothing existing is changed or deleted.
"""

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('records', '0032_embargoed_by_default'),
    ]

    operations = [
        migrations.CreateModel(
            name='ReviewText',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('source_file', models.CharField(max_length=255)),
                ('manuscript_sha256', models.CharField(blank=True, max_length=64)),
                ('state', models.CharField(choices=[('pending', 'Being read'), ('read', 'Read'), ('no_text', 'No text'), ('unavailable', 'Not read yet'), ('not_kept', 'Text not kept')], default='pending', max_length=16)),
                ('reason', models.CharField(blank=True, max_length=32)),
                ('reader', models.CharField(blank=True, max_length=64)),
                ('page_count', models.PositiveIntegerField(blank=True, null=True)),
                ('warnings', models.JSONField(blank=True, default=list)),
                ('read_after_submission', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('read_at', models.DateTimeField(blank=True, null=True)),
                ('record', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='review_texts', to='records.record')),
            ],
            options={
                'ordering': ['record', 'created_at', 'pk'],
            },
        ),
        migrations.AddField(
            model_name='recordversion',
            name='review_text',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.RESTRICT, related_name='versions', to='records.reviewtext'),
        ),
        migrations.CreateModel(
            name='ReviewTextSection',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('ordinal', models.PositiveIntegerField()),
                ('key', models.CharField(max_length=255)),
                ('heading', models.TextField(blank=True)),
                ('page', models.PositiveIntegerField()),
                ('text_hash', models.CharField(max_length=64)),
                ('passages', models.JSONField(default=list)),
                ('text', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sections', to='records.reviewtext')),
            ],
            options={
                'ordering': ['text', 'ordinal'],
            },
        ),
        migrations.AddConstraint(
            model_name='reviewtext',
            constraint=models.CheckConstraint(condition=models.Q(models.Q(('state', 'read'), _negated=True), models.Q(models.Q(('reader', ''), _negated=True), ('read_at__isnull', False)), _connector='OR'), name='review_text_read_names_its_reader'),
        ),
        migrations.AddConstraint(
            model_name='reviewtextsection',
            constraint=models.UniqueConstraint(fields=('text', 'ordinal'), name='review_section_ordinal_unique'),
        ),
        migrations.AddConstraint(
            model_name='reviewtextsection',
            constraint=models.UniqueConstraint(fields=('text', 'key'), name='review_section_key_unique'),
        ),
    ]
