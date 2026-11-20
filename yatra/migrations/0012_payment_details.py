from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('payment', '0003_paymentaccount'),
        ('yatra', '0011_installment_deadlines'),
    ]

    operations = [
        migrations.AddField(
            model_name='yatra',
            name='payment_account',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='yatras',
                to='payment.paymentaccount',
            ),
        ),
        migrations.RemoveField(model_name='yatra', name='payment_upi_id'),
    ]
