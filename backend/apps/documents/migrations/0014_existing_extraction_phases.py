from django.db import migrations


def phases(apps, schema_editor):
    extraction = apps.get_model("documents", "PdfExtraction")
    for status, phase in {"done": "ready", "running": "reading", "failed": "failed"}.items():
        extraction.objects.filter(status=status).update(phase=phase)


class Migration(migrations.Migration):
    dependencies = [("documents", "0013_pdfextraction_attempt_pdfextraction_phase_and_more")]
    operations = [migrations.RunPython(phases, migrations.RunPython.noop)]
