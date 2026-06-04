from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('records', '0007_add_approved_pipeline_status'),
    ]

    operations = [
        migrations.AlterField(
            model_name='record',
            name='pipeline_status',
            field=models.CharField(
                db_index=True,
                default='draft',
                max_length=20,
                choices=[
                    ('draft',          'Draft'),
                    ('adviser_review', 'Adviser Review'),
                    ('approved',       'Approved'),
                    ('completed',      'Completed'),
                    ('rdco_intake',    'RDCO Intake Review'),
                    ('itso_review',    'ITSO Review'),
                    ('parallel_review', 'Parallel Office Review'),
                    ('rdco_review',    'RDCO Final Review'),
                    ('published',      'Published'),
                    ('declined',       'Declined'),
                    ('rejected',       'Rejected'),
                    ('pending_delete', 'Pending Deletion'),
                ],
            ),
        ),
        migrations.AddField(
            model_name='deleterequest',
            name='previous_pipeline_status',
            field=models.CharField(blank=True, default='', max_length=20),
        ),
    ]
