from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('payment', '0004_payment_account_snapshot')]

    operations = [
        migrations.AddField(
            model_name='donation',
            name='payment_account_snapshot',
            field=models.JSONField(blank=True, editable=False, null=True),
        ),
    ]
