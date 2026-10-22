from django.db import migrations, models
import django.db.models.deletion


def seed_baces(apps, schema_editor):
    Bace = apps.get_model('userProfile', 'Bace')
    Profile = apps.get_model('userProfile', 'Profile')

    # Only the fallback Bace is created automatically. Other Baces are
    # configured explicitly by an administrator.
    names = ['Others']
    for name in names:
        bace, _ = Bace.objects.get_or_create(name=name, defaults={'is_active': True})
        if name == 'Others':
            admin_profile = Profile.objects.filter(user__is_superuser=True).first()
            if admin_profile:
                bace.mentors.add(admin_profile)


def backfill_profile_status(apps, schema_editor):
    Profile = apps.get_model('userProfile', 'Profile')
    Profile.objects.filter(user_type__in=['devotee', 'mentor', 'counsellor']).update(
        profile_verification_status='verified'
    )
    Profile.objects.filter(user_type='guest', center__isnull=False).exclude(center='').update(
        profile_verification_status='pending'
    )


class Migration(migrations.Migration):

    dependencies = [
        ('userProfile', '0005_profile_first_connected_center_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='Bace',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=150, unique=True)),
                ('is_active', models.BooleanField(default=True)),
                ('counsellor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='counselled_baces', to='userProfile.profile')),
                ('mentors', models.ManyToManyField(blank=True, related_name='mentor_baces', to='userProfile.profile')),
            ],
        ),
        migrations.RunPython(seed_baces, migrations.RunPython.noop),
        migrations.AddField(
            model_name='profile',
            name='profile_rejection_bace',
            field=models.CharField(blank=True, max_length=150, null=True),
        ),
        migrations.AddField(
            model_name='profile',
            name='profile_verification_status',
            field=models.CharField(choices=[('incomplete', 'Incomplete'), ('pending', 'Pending Verification'), ('verified', 'Verified'), ('rejected', 'Rejected')], default='incomplete', max_length=20),
        ),
        migrations.AddField(
            model_name='mentorrequest',
            name='is_rejected',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='mentorrequest',
            name='rejected_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='mentorrequest',
            name='rejected_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='rejected_mentor_requests', to='userProfile.profile'),
        ),
        migrations.AddField(
            model_name='mentorrequest',
            name='requested_bace',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='mentor_requests', to='userProfile.bace'),
        ),
        migrations.AlterField(
            model_name='profile',
            name='user_type',
            field=models.CharField(choices=[('guest', 'Guest'), ('devotee', 'Devotee'), ('mentor', 'Mentor'), ('counsellor', 'Counsellor')], default='guest', max_length=20),
        ),
        migrations.RunPython(backfill_profile_status, migrations.RunPython.noop),
    ]
