from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("userProfile", "0008_othercenter"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="mentorrequest",
            index=models.Index(
                fields=["requested_bace", "is_approved", "is_rejected"],
                name="mentorreq_bace_status_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="mentorrequest",
            index=models.Index(
                fields=["to_mentor", "is_approved", "is_rejected"],
                name="mentorreq_mentor_status_idx",
            ),
        ),
    ]
