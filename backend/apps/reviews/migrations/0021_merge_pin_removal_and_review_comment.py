"""Join the independent PIN removal and review-comment migrations."""
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("reviews", "0020_delete_recordauthpin"),
        ("reviews", "0020_review_comment"),
    ]

    operations = []
