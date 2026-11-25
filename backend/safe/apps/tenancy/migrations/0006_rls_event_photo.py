"""RLS sulla tabella delle foto degli eventi (rescue.0005): stessa politica delle altre tabelle tenant."""

from django.db import migrations

from safe.apps.tenancy import rls


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0005_rls_person_condition_first_aid"),
        ("rescue", "0005_event_photo"),
    ]
    operations = [rls.run_sql(rls.tenant_table_sql("event_photo"))]
