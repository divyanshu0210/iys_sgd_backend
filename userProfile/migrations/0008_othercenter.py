from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("userProfile", "0007_remove_rejection_metadata"),
    ]

    operations = [
        migrations.CreateModel(
            name="OtherCenter",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=150, unique=True)),
                ("is_active", models.BooleanField(default=True)),
                (
                    "bace",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="other_centers",
                        to="userProfile.bace",
                    ),
                ),
            ],
            options={"ordering": ["name"]},
        ),
    ]
