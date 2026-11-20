from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('yatra_registration', '0005_yatraregistration_phase')]

    operations = [
        migrations.AddField(
            model_name='yatraregistration',
            name='is_complimentary',
            field=models.BooleanField(default=False, help_text='Payment is waived for this guest registration.'),
        ),
    ]
