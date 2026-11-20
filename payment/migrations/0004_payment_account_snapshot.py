from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('payment', '0003_paymentaccount')]

    operations = [
        migrations.AddField(
            model_name='payment',
            name='payment_account_snapshot',
            field=models.JSONField(blank=True, editable=False, null=True),
        ),
    ]
