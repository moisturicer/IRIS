import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reviews', '0012_recordassignment_closed_by_decision'),
    ]

    operations = [
        migrations.AddField(
            model_name='reviewerseat',
            name='closed_by_decision',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.RESTRICT, related_name='closed_seats', to='reviews.review'),
        ),
    ]
