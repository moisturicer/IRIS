"""IR-1099: RDCO's note on a declined delete request.

Additive and reversible: one `varchar(500)` column with a blank default, as
`DownloadRequest.rdco_note` (0023). Every existing row, declined or not, gets
the blank default, which the queue reads as "No note recorded".
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('records', '0040_rebuild_record_views'),
    ]

    operations = [
        migrations.AddField(
            model_name='deleterequest',
            name='rdco_note',
            field=models.CharField(blank=True, default='', max_length=500),
        ),
    ]
