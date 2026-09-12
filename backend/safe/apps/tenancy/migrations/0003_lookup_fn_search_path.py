"""assert_lookup_dimension() è usata nei CHECK delle tabelle e cerca `lookup_value` senza schema: durante un
ripristino da pg_dump (che azzera search_path) i COPY fallivano con "relation lookup_value does not exist".
Fissando search_path sulla funzione il ripristino funziona senza accorgimenti."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("tenancy", "0002_rls")]
    operations = [
        migrations.RunSQL(
            "ALTER FUNCTION assert_lookup_dimension(uuid, text) SET search_path = public;",
            "ALTER FUNCTION assert_lookup_dimension(uuid, text) RESET search_path;",
        )
    ]
