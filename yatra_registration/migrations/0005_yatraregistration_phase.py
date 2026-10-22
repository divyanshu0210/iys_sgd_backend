from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("yatra", "0009_registration_phases"),
        ("yatra_registration", "0004_remove_rcsdownloadevent_yatra_regis_created_ff6a53_idx_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="yatraregistration",
            name="phase",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="registrations",
                to="yatra.registrationphase",
            ),
        ),
    ]
