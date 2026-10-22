from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("userProfile", "0006_bace_profile_verification"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="profile",
            name="profile_rejection_bace",
        ),
    ]
