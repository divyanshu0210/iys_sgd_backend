from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("yatra", "0008_yatra_poster"),
    ]

    operations = [
        migrations.CreateModel(
            name="RegistrationPhase",
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
                ("name", models.CharField(max_length=150)),
                ("start_date", models.DateField()),
                ("end_date", models.DateField(blank=True, null=True)),
                ("order", models.PositiveIntegerField(default=0)),
                (
                    "yatra",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="registration_phases",
                        to="yatra.yatra",
                    ),
                ),
            ],
            options={
                "ordering": ["order", "start_date", "id"],
            },
        ),
        migrations.AddConstraint(
            model_name="registrationphase",
            constraint=models.UniqueConstraint(
                fields=("yatra", "name"),
                name="unique_yatra_registration_phase_name",
            ),
        ),
        migrations.AddField(
            model_name="yatrainstallment",
            name="phase",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="installments",
                to="yatra.registrationphase",
            ),
        ),
        migrations.AddField(
            model_name="yatrainstallment",
            name="start_date",
            field=models.DateField(
                blank=True,
                null=True,
                help_text="After this date, this installment becomes compulsory for this phase.",
            ),
        ),
        migrations.AlterUniqueTogether(
            name="yatrainstallment",
            unique_together=set(),
        ),
        migrations.AddConstraint(
            model_name="yatrainstallment",
            constraint=models.UniqueConstraint(
                fields=("yatra", "phase", "label"),
                name="unique_yatra_phase_installment_label",
            ),
        ),
    ]
