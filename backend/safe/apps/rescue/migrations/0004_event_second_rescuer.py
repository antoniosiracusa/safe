from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("rescue", "0003_person_condition_first_aid"),
    ]

    operations = [
        migrations.AddField(
            model_name="event",
            name="second_rescuer",
            field=models.CharField(blank=True, default="", max_length=120),
        ),
    ]
