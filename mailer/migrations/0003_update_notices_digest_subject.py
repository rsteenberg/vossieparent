from django.db import migrations


def forwards(apps, schema_editor):
    EmailTemplate = apps.get_model("mailer", "EmailTemplate")
    EmailTemplate.objects.filter(key="notices_digest").update(
        subject_template="{subject}",
    )


def backwards(apps, schema_editor):
    EmailTemplate = apps.get_model("mailer", "EmailTemplate")
    EmailTemplate.objects.filter(
        key="notices_digest",
        subject_template="{subject}",
    ).update(subject_template="Your Eduvos notices ({total})")


class Migration(migrations.Migration):

    dependencies = [
        ("mailer", "0002_messagelog"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
