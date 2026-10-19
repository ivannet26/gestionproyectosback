from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [("absences", "0001_initial")]

    operations = [
        migrations.RunSQL(
            "ALTER TABLE ausencia ADD COLUMN aprobada TINYINT(1) NULL DEFAULT NULL",
            "ALTER TABLE ausencia DROP COLUMN aprobada",
        ),
    ]
