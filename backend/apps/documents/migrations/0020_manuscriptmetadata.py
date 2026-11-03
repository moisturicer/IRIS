# IR-846: LlamaExtract's reading of a parsed Manuscript revision.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('documents', '0019_pdfextraction_raw_result'),
    ]

    operations = [
        migrations.CreateModel(
            name='ManuscriptMetadata',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('source_revision', models.UUIDField(editable=False)),
                ('status', models.CharField(choices=[('queued', 'Queued'), ('running', 'Running'), ('done', 'Done'), ('failed', 'Failed'), ('refused', 'Refused')], default='queued', max_length=10)),
                ('attempt', models.UUIDField(blank=True, editable=False, null=True)),
                ('result', models.JSONField(blank=True, default=dict)),
                ('credits', models.DecimalField(blank=True, decimal_places=3, max_digits=12, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('extraction', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='metadata_readings', to='documents.pdfextraction')),
            ],
            options={
                'constraints': [models.UniqueConstraint(fields=('extraction', 'source_revision'), name='manuscriptmetadata_one_per_revision')],
            },
        ),
    ]
