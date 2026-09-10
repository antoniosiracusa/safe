import datetime as dt

from django.db import migrations


def seed(apps, schema_editor):
    Season = apps.get_model("rescue", "Season")
    for start_year in range(2018, 2028):
        Season.objects.get_or_create(
            code=f"{start_year}/{start_year + 1}",
            defaults={"start_date": dt.date(start_year, 6, 1), "end_date": dt.date(start_year + 1, 5, 31)},
        )


class Migration(migrations.Migration):
    dependencies = [("rescue", "0001_initial"), ("tenancy", "0002_rls")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
