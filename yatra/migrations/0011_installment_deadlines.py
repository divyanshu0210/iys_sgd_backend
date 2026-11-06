from django.db import migrations, models


def copy_phase_dates(apps, schema_editor):
    Phase = apps.get_model('yatra', 'RegistrationPhase')
    Installment = apps.get_model('yatra', 'YatraInstallment')
    for phase in Phase.objects.order_by('id').iterator():
        first = Installment.objects.filter(phase_id=phase.pk).order_by('order', 'id').first()
        if not first:
            raise RuntimeError(f'Phase {phase.pk} has no installment; add one before migrating its dates.')
        first.start_date = phase.start_date
        first.end_date = phase.end_date
        first.save(update_fields=['start_date', 'end_date'])


class Migration(migrations.Migration):
    dependencies = [('yatra', '0010_remove_phase_order_and_full_payment_date')]
    operations = [
        migrations.AddField(model_name='yatrainstallment', name='end_date', field=models.DateField(blank=True, null=True, help_text='Last day to submit payment proof; the first installment also closes registration for this phase.')),
        migrations.RunPython(copy_phase_dates, migrations.RunPython.noop),
        migrations.AlterModelOptions(name='registrationphase', options={'ordering': ['id']}),
        migrations.RemoveField(model_name='registrationphase', name='start_date'),
        migrations.RemoveField(model_name='registrationphase', name='end_date'),
    ]
