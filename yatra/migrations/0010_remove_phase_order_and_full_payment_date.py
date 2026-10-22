from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("yatra", "0009_registration_phases"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="registrationphase",
            name="order",
        ),
        migrations.RemoveField(
            model_name="yatra",
            name="accept_full_payment_only_date",
        ),
    ]
