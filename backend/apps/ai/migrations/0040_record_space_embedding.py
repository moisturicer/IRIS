"""Space-keyed Record vectors, beside the legacy table (IR-752, ADR-049 §23).

Expand only. ``ai_recordembedding`` keeps every row and every caller; this adds
``ai_recordspaceembedding`` keyed by ``(record, space)`` so a second Embedding
Space can hold summary vectors without overwriting the live one.

The data step copies each legacy vector under the space whose ``model_id`` equals
the row's ``model_name`` (the active one first, else the newest retired one; a
pending space is never a target). A row whose model matches no space is left
only in the legacy table, where every reader still finds it. Copied rows carry
``source_hash = ''``: the text they were embedded from is not recorded, so no
freshness is claimed. The reverse drops the new table with the schema step and
needs no data step.
"""

import django.db.models.deletion
import pgvector.django.indexes
import pgvector.django.vector
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ai', '0039_chunkset_source_revision'),
        ('records', '0031_version_documents'),
    ]

    operations = [
        migrations.CreateModel(
            name='RecordSpaceEmbedding',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('embedding', pgvector.django.vector.VectorField(dimensions=1024)),
                ('source_hash', models.CharField(blank=True, max_length=64)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('record', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='space_embeddings', to='records.record')),
                ('space', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='record_embeddings', to='ai.embeddingspace')),
            ],
            options={
                'indexes': [pgvector.django.indexes.HnswIndex(ef_construction=64, fields=['embedding'], m=16, name='record_space_embedding_hnsw_idx', opclasses=['vector_cosine_ops'])],
                'constraints': [models.UniqueConstraint(fields=('record', 'space'), name='unique_record_embedding_per_space')],
            },
        ),
        migrations.RunSQL(
            sql="""
            INSERT INTO ai_recordspaceembedding
                (record_id, space_id, embedding, source_hash, created_at, updated_at)
            SELECT e.record_id, s.id, e.embedding, '', e.created_at, e.updated_at
            FROM ai_recordembedding e
            JOIN LATERAL (
                SELECT id FROM ai_embeddingspace
                WHERE model_id = e.model_name AND state IN ('active', 'retired')
                ORDER BY (state = 'active') DESC, id DESC
                LIMIT 1
            ) s ON TRUE
            ON CONFLICT (record_id, space_id) DO NOTHING
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
