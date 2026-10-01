from django.db import migrations


DJANGO_TABLES = (
    "api_cliente",
    "api_eventoagenda",
    "api_processo",
    "auditlog_eventoauditoria",
    "auth_group",
    "auth_group_permissions",
    "auth_permission",
    "auth_user",
    "auth_user_groups",
    "auth_user_user_permissions",
    "django_admin_log",
    "django_content_type",
    "django_migrations",
    "django_session",
    "organizations_escritorio",
    "organizations_membroescritorio",
)


def restringir_api_publica_supabase(apps, schema_editor):
    connection = schema_editor.connection
    if connection.vendor != "postgresql":
        return

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT rolname FROM pg_roles WHERE rolname IN ('anon', 'authenticated')"
        )
        roles = {row[0] for row in cursor.fetchall()}
        if roles != {"anon", "authenticated"}:
            return

        quote = connection.ops.quote_name
        for table in DJANGO_TABLES:
            cursor.execute(
                f"REVOKE ALL PRIVILEGES ON TABLE {quote(table)} "
                "FROM anon, authenticated"
            )
            cursor.execute(f"ALTER TABLE {quote(table)} ENABLE ROW LEVEL SECURITY")

        cursor.execute(
            "REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public "
            "FROM anon, authenticated"
        )
        cursor.execute(
            "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
            "REVOKE ALL PRIVILEGES ON TABLES FROM anon, authenticated"
        )
        cursor.execute(
            "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
            "REVOKE ALL PRIVILEGES ON SEQUENCES FROM anon, authenticated"
        )


class Migration(migrations.Migration):
    dependencies = [("api", "0006_office_owned_data")]

    operations = [
        migrations.RunPython(
            restringir_api_publica_supabase,
            reverse_code=migrations.RunPython.noop,
        )
    ]
