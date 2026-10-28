from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("yatra_substitution", "0001_initial")]

    operations = [
        migrations.AlterField(
            model_name="substitutionrequest",
            name="two_digit_code",
            field=models.CharField(max_length=6),
        ),
        migrations.AddField(
            model_name="substitutionrequest",
            name="failed_code_attempts",
            field=models.PositiveSmallIntegerField(default=0),
        ),
    ]
