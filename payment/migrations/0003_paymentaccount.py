from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('payment', '0002_donation')]

    operations = [
        migrations.CreateModel(
            name='PaymentAccount',
            fields=[
                ('id', models.AutoField(primary_key=True, serialize=False)),
                ('account_name', models.CharField(blank=True, default='', max_length=255)),
                ('account_number', models.CharField(blank=True, default='', max_length=100)),
                ('ifsc', models.CharField(blank=True, default='', max_length=20)),
                ('bank_name', models.CharField(blank=True, default='', max_length=255)),
                ('upi_id', models.CharField(blank=True, default='', max_length=255)),
                ('is_global', models.BooleanField(default=False)),
            ],
            options={
                'constraints': [models.UniqueConstraint(
                    fields=('is_global',), condition=models.Q(is_global=True),
                    name='payment_single_global_account',
                )],
            },
        ),
    ]
