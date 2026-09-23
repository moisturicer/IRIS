"""Document `Turn.state`'s values as `choices`, adding `partial` (IR-328).

No data changes: existing rows already only ever held `generated`,
`no_sources` or `unavailable`, and the column stays a plain `CharField`.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ai', '0012_turn_had_reasoning'),
    ]

    operations = [
        migrations.AlterField(
            model_name='turn',
            name='state',
            field=models.CharField(choices=[('generated', 'Generated'), ('no_sources', 'No sources'), ('unavailable', 'Unavailable'), ('partial', 'Partial')], max_length=20),
        ),
    ]
